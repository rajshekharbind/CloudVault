import io
import json
import os
import re
import urllib.parse
import urllib.request
import zipfile

from PIL import Image
from django.shortcuts import render, get_object_or_404, redirect
from django.http import FileResponse, JsonResponse, HttpResponse, Http404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.utils import timezone
from django.db.models import Q, Sum, Count
from django.core.files.base import ContentFile
from django.utils.text import slugify
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import Folder, FileItem, FileVersion, SentinelScan, ExternalUrlScan
from .security_rag import generate_rag_security_report
from sharing.models import Collaborator
from .serializers import FolderSerializer, FileItemSerializer, FileVersionSerializer
from .utils import (
    detect_file_category,
    calculate_checksum,
    generate_image_thumbnail,
    format_bytes
)
from analytics.models import ActivityLog, Notification
from sharing.models import ShareLink
from django.contrib.auth import get_user_model

User = get_user_model()

def helper_get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def _scan_for_sensitive_content(file_name, uploaded_file):
    factors = []
    risk_score = 0
    lowered_name = (file_name or '').lower()

    suspicious_tokens = [
        'password', 'secret', 'token', 'credential', 'accesskey', 'private',
        'aws', 'dbpass', 'apikey', 'authkey', 'oauth', 'api_key', 'prod', 'confidential'
    ]
    for token in suspicious_tokens:
        if token in lowered_name:
            risk_score += 15
            factors.append(f"filename_contains:{token}")

    suspicious_extensions = {'exe', 'dll', 'bat', 'cmd', 'com', 'scr', 'ps1', 'js', 'vbs', 'jar'}
    ext = os.path.splitext(file_name or '')[1].lower().lstrip('.')
    if ext in suspicious_extensions:
        risk_score += 30
        factors.append(f"suspicious_extension:{ext}")

    if uploaded_file is not None:
        try:
            file_obj = uploaded_file.file if hasattr(uploaded_file, 'file') else uploaded_file
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
                sample = file_obj.read(20000)
                if hasattr(file_obj, 'seek'):
                    file_obj.seek(0)
                if isinstance(sample, (bytes, bytearray)):
                    sample_text = sample.decode('utf-8', errors='ignore')
                else:
                    sample_text = str(sample)
                patterns = [
                    r'AKIA[0-9A-Z]{16}', r'aws[_-]?secret[_-]?access[_-]?key',
                    r'-----BEGIN [A-Z ]*PRIVATE KEY-----', r'(?i)(password|passwd|secret|token)\s*[:=]\s*[A-Za-z0-9!@#$%^&*()_+\-={}\[\]:;"\'\\|,.<>/?~`]{4,}',
                    r'(?i)api[_-]?key\s*[:=]\s*[A-Za-z0-9._\-]{8,}'
                ]
                import re
                for pattern in patterns:
                    if re.search(pattern, sample_text):
                        risk_score += 30
                        factors.append(f"content_pattern:{pattern}")
        except Exception:
            pass

    rag_report = generate_rag_security_report(file_name, os.path.splitext(file_name or '')[1].lower(), factors)
    risk_score = min(max(risk_score + rag_report['risk_adjustment'], 0), 100)

    if risk_score >= 80:
        status = 'blocked'
        level = 'critical'
        summary = 'CloudVault Sentinel flagged the object as high-risk due to suspicious naming, risky file type, sensitive material detection, and policy-risk correlation.'
        recommendation = 'The object has been blocked from trusted storage to prevent malware or credential leakage.'
    elif risk_score >= 45:
        status = 'manual_review'
        level = 'high'
        summary = 'CloudVault Sentinel detected suspicious indicators and routed the object for a human security review using its policy knowledge base.'
        recommendation = 'A security analyst should verify the content, ownership, and policy risk before approving access.'
    else:
        status = 'approved'
        level = 'low'
        summary = 'CloudVault Sentinel completed a safe-content review and approved the object for trusted storage.'
        recommendation = 'Continue standard monitoring and keep the object within the approved policy baseline.'

    if rag_report['policy_hits']:
        summary = rag_report['agent_summary']
        recommendation = '; '.join(rag_report['recommendations'])

    return {
        'status': status,
        'risk_score': min(risk_score, 100),
        'risk_level': level,
        'summary': summary,
        'recommendations': recommendation,
        'findings': {'factors': factors},
        'quarantine_required': status in ['manual_review', 'blocked'],
        'rag_policy_hits': rag_report['policy_hits'],
        'agent_summary': rag_report['agent_summary'],
    }


def run_sentinel_scan(file_item):
    scan_result = _scan_for_sensitive_content(file_item.name, file_item.file)
    file_item.security_status = scan_result['status']
    file_item.risk_score = scan_result['risk_score']
    file_item.is_quarantined = scan_result['quarantine_required']
    file_item.quarantine_reason = scan_result['summary']
    file_item.security_summary = scan_result['summary']
    file_item.save(update_fields=['security_status', 'risk_score', 'is_quarantined', 'quarantine_reason', 'security_summary', 'updated_at'])

    SentinelScan.objects.create(
        file_item=file_item,
        status=scan_result['status'],
        risk_score=scan_result['risk_score'],
        risk_level=scan_result['risk_level'],
        summary=scan_result['summary'],
        findings=scan_result['findings'],
        recommendations=scan_result['recommendations'],
        quarantine_required=scan_result['quarantine_required'],
    )
    return scan_result


def scan_url_for_safety(raw_url, user):
    if not raw_url or not str(raw_url).strip():
        raise ValueError('A URL is required to run a security scan.')

    candidate = str(raw_url).strip()
    if '://' not in candidate:
        candidate = 'https://' + candidate

    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('Only http/https URLs are supported for security scanning.')

    blocked_domains = ['tinyurl.com', 'bit.ly', 'goo.gl', 'ow.ly', 'is.gd', 't.co']
    lowered = candidate.lower()
    findings = []
    risk_score = 0
    redirect_chain = []
    final_url = candidate
    response_status = 0
    body = b''
    quarantine_filename = ''

    if any(domain in lowered for domain in blocked_domains):
        risk_score += 25
        findings.append('url_shortener_domain')

    suspicious_tokens = ['download', 'confirm', 'verify', 'secure', 'free', 'claim', 'login', 'account', 'password', 'invoice', 'urgent', 'click-here']
    for token in suspicious_tokens:
        if token in lowered:
            risk_score += 8
            findings.append(f'url_keyword:{token}')

    suspicious_exts = ['.exe', '.dll', '.bat', '.cmd', '.scr', '.msi', '.apk', '.jar', '.ps1', '.vbs']
    if any(candidate.lower().endswith(ext) for ext in suspicious_exts):
        risk_score += 35
        findings.append('suspicious_file_extension')

    browser_html = ''
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(candidate, wait_until='domcontentloaded', timeout=15000)
            browser_html = page.content()
            final_url = page.url or final_url
            browser.close()
    except Exception:
        browser_html = ''

    request = urllib.request.Request(candidate, headers={
        'User-Agent': 'CloudVault-Sentinel/1.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            final_url = response.geturl() or candidate
            response_status = getattr(response, 'status', 0)
            body = response.read(2 * 1024 * 1024)
            redirect_chain = [candidate]
            if final_url and final_url != candidate:
                redirect_chain.append(final_url)

        if response_status >= 400:
            risk_score += 25
            findings.append('http_error_response')

        if len(redirect_chain) > 3:
            risk_score += 20
            findings.append('many_redirects')

        browser_text = browser_html.lower()
        if 'javascript:' in lowered or 'onclick' in (body.decode('utf-8', 'ignore').lower() + ' ' + browser_text):
            risk_score += 20
            findings.append('script_based_redirect')

        if body or browser_html:
            html_snippet = (body.decode('utf-8', 'ignore') + ' ' + browser_html).lower()
            for pattern in ['login', 'verify', 'urgent', 'download', 'suspicious', 'free']:
                if pattern in html_snippet:
                    risk_score += 10
                    findings.append(f'page_content_hint:{pattern}')

            suspicious_content = _scan_for_sensitive_content(os.path.basename(urllib.parse.urlparse(final_url).path) or 'remote-download', ContentFile(body, name='remote-download'))
            if suspicious_content['risk_score'] > 0:
                risk_score += min(suspicious_content['risk_score'] // 2, 30)
                findings.append('downloaded_content_suspicious')

        rag_report = generate_rag_security_report(
            urllib.parse.urlparse(final_url).path or candidate,
            'url',
            findings,
            url=candidate,
        )
        risk_score = min(max(risk_score + rag_report['risk_adjustment'], 0), 100)

        if final_url.lower().endswith(('.exe', '.dll', '.bat', '.cmd', '.scr', '.msi', '.apk', '.jar', '.ps1', '.vbs')):
            risk_score += 40
            findings.append('final_url_is_binary')

    except Exception as exc:
        risk_score += 20
        findings.append(f'network_error:{type(exc).__name__}')
        summary = 'CloudVault Sentinel could not validate the URL safely and flagged it for manual review because the remote endpoint did not respond cleanly.'
        decision = 'manual_review'
        result = {
            'status': decision,
            'risk_score': min(risk_score, 100),
            'risk_level': 'high',
            'summary': summary,
            'final_url': final_url,
            'redirect_chain': redirect_chain,
            'findings': {'factors': findings},
            'quarantine_required': True,
            'rag_policy_hits': [],
            'agent_summary': 'The AI Security Agent flagged the URL as untrustworthy due to a validation failure or suspicious remote behavior.',
        }
        ExternalUrlScan.objects.create(
            owner=user,
            url=candidate,
            final_url=final_url,
            http_status=response_status,
            redirect_chain=redirect_chain,
            status=decision,
            risk_score=result['risk_score'],
            risk_level=result['risk_level'],
            summary=summary,
            findings=result['findings'],
            quarantined_file=None,
        )
        return result

    rag_report = generate_rag_security_report(
        urllib.parse.urlparse(final_url).path or candidate,
        'url',
        findings,
        url=candidate,
    )
    risk_score = min(max(risk_score + rag_report['risk_adjustment'], 0), 100)

    if risk_score >= 80:
        decision = 'blocked'
        risk_level = 'critical'
        summary = 'CloudVault Sentinel blocked the URL because it matched known malicious indicators, suspicious redirects, or executable download patterns.'
    elif risk_score >= 45:
        decision = 'manual_review'
        risk_level = 'high'
        summary = 'CloudVault Sentinel flagged the URL for human review because the destination was overly risky or redirect-heavy.'
    else:
        decision = 'approved'
        risk_level = 'low'
        summary = 'CloudVault Sentinel validated the URL and approved it for standard access.'

    if rag_report['policy_hits']:
        summary = rag_report['agent_summary']

    if body:
        quarantine_dir = os.path.join(settings.MEDIA_ROOT, 'quarantine')
        os.makedirs(quarantine_dir, exist_ok=True)
        quarantine_filename = slugify(urllib.parse.urlparse(final_url).netloc or 'remote-download') + '-sentinel.bin'
        preserved_path = os.path.join(quarantine_dir, quarantine_filename)
        with open(preserved_path, 'wb') as quarantine_file:
            quarantine_file.write(body[:5 * 1024 * 1024])

    url_scan = ExternalUrlScan.objects.create(
        owner=user,
        url=candidate,
        final_url=final_url,
        http_status=response_status,
        redirect_chain=redirect_chain,
        status=decision,
        risk_score=min(risk_score, 100),
        risk_level=risk_level,
        summary=summary,
        findings={'factors': findings},
        quarantined_file=None,
    )

    if body and quarantine_filename:
        preserved_path = os.path.join(settings.MEDIA_ROOT, 'quarantine', quarantine_filename)
        if os.path.exists(preserved_path):
            with open(preserved_path, 'rb') as quarantine_file:
                url_scan.quarantined_file.save(
                    quarantine_filename,
                    ContentFile(quarantine_file.read()),
                    save=True,
                )

    return {
        'status': decision,
        'risk_score': min(risk_score, 100),
        'risk_level': risk_level,
        'summary': summary,
        'final_url': final_url,
        'redirect_chain': redirect_chain,
        'findings': {'factors': findings},
        'quarantine_required': decision in ['manual_review', 'blocked'],
        'scan_id': url_scan.id,
        'rag_policy_hits': rag_report['policy_hits'],
        'agent_summary': rag_report['agent_summary'],
    }


@login_required
def scan_url_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are allowed.'}, status=405)

    payload = request.POST.get('url')
    if not payload and hasattr(request, 'data'):
        payload = request.data.get('url')
    if not payload:
        return JsonResponse({'error': 'A URL is required.'}, status=400)

    try:
        result = scan_url_for_safety(payload, request.user)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    return JsonResponse(result)


@login_required
def security_agent_analysis_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are allowed.'}, status=405)

    file_name = (request.POST.get('file_name') or request.data.get('file_name') or '').strip()
    file_type = (request.POST.get('file_type') or request.data.get('file_type') or 'unknown').strip()
    findings = request.POST.getlist('findings') or (request.data.getlist('findings') if hasattr(request.data, 'getlist') else [])
    url = (request.POST.get('url') or request.data.get('url') or '').strip()

    if not file_name and not url:
        return JsonResponse({'error': 'file_name or url is required.'}, status=400)

    report = generate_rag_security_report(file_name or (url or 'remote-url'), file_type or 'url', findings or [], url=url or None)
    return JsonResponse(report)


# Page Template Views
@login_required
def dashboard_view(request):
    user = request.user
    recent_files = FileItem.objects.filter(owner=user, is_trashed=False).order_by('-created_at')[:8]
    recent_activities = ActivityLog.objects.filter(user=user)[:6]

    # File types storage stats
    stats_qs = FileItem.objects.filter(owner=user, is_trashed=False).values('file_type').annotate(
        total_bytes=Sum('file_size'),
        count=Count('id')
    )

    stats_by_type = {
        'image': 0, 'video': 0, 'audio': 0, 'pdf': 0,
        'document': 0, 'spreadsheet': 0, 'archive': 0, 'other': 0
    }
    for item in stats_qs:
        ftype = item['file_type']
        if ftype in stats_by_type:
            stats_by_type[ftype] += item['total_bytes'] or 0
        else:
            stats_by_type['other'] += item['total_bytes'] or 0

    total_files_count = FileItem.objects.filter(owner=user, is_trashed=False).count()
    total_folders_count = Folder.objects.filter(owner=user, is_trashed=False).count()
    notifications = Notification.objects.filter(user=user, is_read=False)[:5]

    sentinel_scans = SentinelScan.objects.filter(file_item__owner=user).order_by('-created_at')[:5]
    blocked_files = FileItem.objects.filter(owner=user, is_trashed=False, security_status='blocked').count()
    review_files = FileItem.objects.filter(owner=user, is_trashed=False, security_status='manual_review').count()
    approved_files = FileItem.objects.filter(owner=user, is_trashed=False, security_status='approved').count()

    context = {
        'recent_files': recent_files,
        'recent_activities': recent_activities,
        'stats_by_type': stats_by_type,
        'total_files_count': total_files_count,
        'total_folders_count': total_folders_count,
        'notifications': notifications,
        'sentinel_scans': sentinel_scans,
        'blocked_files': blocked_files,
        'review_files': review_files,
        'approved_files': approved_files,
    }
    return render(request, 'dashboard.html', context)


@login_required
def files_view(request):
    user = request.user
    folder_id = request.GET.get('folder')
    search_query = request.GET.get('q', '').strip()
    filter_type = request.GET.get('type', '')
    sort_by = request.GET.get('sort', '-updated_at')

    current_folder = None
    if folder_id:
        current_folder = get_object_or_404(Folder, id=folder_id, owner=user, is_trashed=False)

    folders_qs = Folder.objects.filter(owner=user, is_trashed=False)
    files_qs = FileItem.objects.filter(owner=user, is_trashed=False)

    if current_folder:
        folders_qs = folders_qs.filter(parent=current_folder)
        files_qs = files_qs.filter(folder=current_folder)
    elif not search_query and not filter_type:
        folders_qs = folders_qs.filter(parent=None)
        files_qs = files_qs.filter(folder=None)

    if search_query:
        folders_qs = folders_qs.filter(name__icontains=search_query)
        files_qs = files_qs.filter(Q(name__icontains=search_query) | Q(tags__icontains=search_query))

    if filter_type:
        files_qs = files_qs.filter(file_type=filter_type)

    if sort_by in ['name', '-name', 'created_at', '-created_at', 'file_size', '-file_size', 'updated_at', '-updated_at']:
        files_qs = files_qs.order_by(sort_by)

    ancestors = current_folder.get_ancestors() if current_folder else []

    filter_choices = [
        ('', 'All'),
        ('image', 'Images'),
        ('video', 'Videos'),
        ('audio', 'Audio'),
        ('pdf', 'PDF'),
        ('document', 'Documents'),
        ('spreadsheet', 'Spreadsheets'),
        ('presentation', 'Presentations'),
        ('archive', 'Archives'),
        ('code', 'Code'),
    ]

    context = {
        'current_folder': current_folder,
        'folders': folders_qs,
        'files': files_qs,
        'ancestors': ancestors,
        'search_query': search_query,
        'filter_type': filter_type,
        'sort_by': sort_by,
        'filter_choices': filter_choices,
    }
    return render(request, 'files.html', context)



@login_required
def favorites_view(request):
    user = request.user
    folders = Folder.objects.filter(owner=user, is_favorite=True, is_trashed=False)
    files = FileItem.objects.filter(owner=user, is_favorite=True, is_trashed=False)
    context = {'folders': folders, 'files': files}
    return render(request, 'favorites.html', context)


@login_required
def shared_view(request):
    user = request.user
    my_shares = ShareLink.objects.filter(created_by=user)
    context = {'my_shares': my_shares}
    return render(request, 'shared.html', context)


@login_required
def trash_view(request):
    user = request.user
    trashed_folders = Folder.objects.filter(owner=user, is_trashed=True).order_by('-trashed_at')
    trashed_files = FileItem.objects.filter(owner=user, is_trashed=True).order_by('-trashed_at')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'empty_trash':
            # Permanently delete all trashed files & folders for user
            for f in trashed_files:
                if f.file and os.path.exists(f.file.path):
                    try:
                        os.remove(f.file.path)
                    except Exception:
                        pass
                f.delete()
            for fold in trashed_folders:
                fold.delete()
            messages.success(request, 'Trash emptied permanently.')
            ActivityLog.log_activity(
                user=user,
                action='PERMANENT_DELETE',
                details={'scope': 'empty_trash'},
                ip_address=helper_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            return redirect('trash')

    context = {
        'trashed_folders': trashed_folders,
        'trashed_files': trashed_files
    }
    return render(request, 'trash.html', context)


@login_required
def analytics_view(request):
    user = request.user
    # Storage usage breakdown
    files_by_type = FileItem.objects.filter(owner=user, is_trashed=False).values('file_type').annotate(
        size=Sum('file_size'), count=Count('id')
    )
    largest_files = FileItem.objects.filter(owner=user, is_trashed=False).order_by('-file_size')[:5]
    activities = ActivityLog.objects.filter(user=user)[:15]

    context = {
        'files_by_type': list(files_by_type),
        'largest_files': largest_files,
        'activities': activities,
    }
    return render(request, 'analytics.html', context)


@login_required
def sentinel_dashboard_view(request):
    user = request.user
    scans = SentinelScan.objects.filter(file_item__owner=user).order_by('-created_at')[:20]
    url_scans = ExternalUrlScan.objects.filter(owner=user).order_by('-created_at')[:10]

    latest_files = FileItem.objects.filter(owner=user, is_trashed=False).order_by('-updated_at')[:10]
    low_risk = FileItem.objects.filter(owner=user, is_trashed=False, risk_score__lt=50).count()
    medium_risk = FileItem.objects.filter(owner=user, is_trashed=False, risk_score__gte=50, risk_score__lt=80).count()
    high_risk = FileItem.objects.filter(owner=user, is_trashed=False, risk_score__gte=80).count()

    context = {
        'scans': scans,
        'url_scans': url_scans,
        'latest_files': latest_files,
        'low_risk': low_risk,
        'medium_risk': medium_risk,
        'high_risk': high_risk,
        'total_scans': scans.count() + url_scans.count(),
    }
    return render(request, 'sentinel.html', context)


@login_required
def admin_panel_view(request):
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, 'Access restricted to administrators.')
        return redirect('dashboard')

    users = User.objects.all().order_by('-date_joined')
    total_users = users.count()
    total_files = FileItem.objects.filter(is_trashed=False).count()
    total_storage = FileItem.objects.filter(is_trashed=False).aggregate(total=Sum('file_size'))['total'] or 0

    if request.method == 'POST':
        action = request.POST.get('action')
        target_user_id = request.POST.get('user_id')
        if action == 'toggle_block' and target_user_id:
            target_user = get_object_or_404(User, id=target_user_id)
            target_user.is_blocked = not target_user.is_blocked
            target_user.save()
            messages.success(request, f"User {target_user.username} {'blocked' if target_user.is_blocked else 'unblocked'}.")
            return redirect('admin_panel')

    context = {
        'users': users,
        'total_users': total_users,
        'total_files': total_files,
        'total_storage_fmt': format_bytes(total_storage),
    }
    return render(request, 'admin_panel.html', context)


# File Streaming & Preview Views
@login_required
def download_file_view(request, file_id):
    file_item = get_object_or_404(FileItem, id=file_id, owner=request.user, is_trashed=False)
    if not file_item.file or not os.path.exists(file_item.file.path):
        raise Http404("File does not exist.")

    ActivityLog.log_activity(
        user=request.user,
        action='DOWNLOAD',
        details={'file_name': file_item.name, 'file_id': file_item.id},
        ip_address=helper_get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    return FileResponse(open(file_item.file.path, 'rb'), as_attachment=True, filename=file_item.original_name)


@login_required
def preview_file_content_view(request, file_id):
    file_item = get_object_or_404(FileItem, id=file_id, owner=request.user, is_trashed=False)
    if not file_item.file or not os.path.exists(file_item.file.path):
        return JsonResponse({'error': 'File not found'}, status=404)

    if file_item.file_type in ['code', 'text']:
        try:
            with open(file_item.file.path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(50000)  # Read max 50KB
            return JsonResponse({'type': 'text', 'content': content})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({
        'type': file_item.file_type,
        'url': file_item.file.url,
        'name': file_item.name,
        'size': file_item.formatted_size()
    })


# REST APIs & File Operations
class UploadFileAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        uploaded_files = request.FILES.getlist('files') or ([request.FILES.get('file')] if request.FILES.get('file') else [])
        folder_id = request.data.get('folder_id')

        if not uploaded_files:
            return Response({'error': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        folder = None
        if folder_id:
            folder = get_object_or_404(Folder, id=folder_id, owner=request.user, is_trashed=False)

        created_file_items = []
        user = request.user

        for uploaded_file in uploaded_files:
            # Check user storage quota
            if user.storage_used + uploaded_file.size > user.storage_quota:
                return Response({'error': f'Storage quota exceeded for file {uploaded_file.name}.'}, status=status.HTTP_400_BAD_REQUEST)

            ext = os.path.splitext(uploaded_file.name)[1].lower()
            category = detect_file_category(ext, uploaded_file.content_type)
            checksum = calculate_checksum(uploaded_file)
            scan_result = _scan_for_sensitive_content(uploaded_file.name, uploaded_file)

            if scan_result['status'] == 'blocked':
                return Response({
                    'error': f'CloudVault Sentinel blocked {uploaded_file.name}. {scan_result["summary"]}',
                    'risk_score': scan_result['risk_score'],
                    'status': 'blocked',
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check if version update requested or identical file upload
            existing_file = FileItem.objects.filter(
                owner=user, folder=folder, name=uploaded_file.name, is_trashed=False
            ).first()

            if existing_file:
                existing_file.create_version(uploaded_file, user, changelog="Uploaded duplicate name file version")
                existing_file.security_status = scan_result['status']
                existing_file.risk_score = scan_result['risk_score']
                existing_file.is_quarantined = scan_result['quarantine_required']
                existing_file.quarantine_reason = scan_result['summary']
                existing_file.security_summary = scan_result['summary']
                existing_file.save(update_fields=['security_status', 'risk_score', 'is_quarantined', 'quarantine_reason', 'security_summary', 'updated_at'])
                SentinelScan.objects.create(
                    file_item=existing_file,
                    status=scan_result['status'],
                    risk_score=scan_result['risk_score'],
                    risk_level=scan_result['risk_level'],
                    summary=scan_result['summary'],
                    findings=scan_result['findings'],
                    recommendations=scan_result['recommendations'],
                    quarantine_required=scan_result['quarantine_required'],
                )
                created_file_items.append(existing_file)
                ActivityLog.log_activity(
                    user=user,
                    action='UPLOAD',
                    details={'file_name': existing_file.name, 'version': existing_file.current_version, 'security_status': scan_result['status']},
                    ip_address=helper_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
            else:
                file_item = FileItem(
                    name=uploaded_file.name,
                    original_name=uploaded_file.name,
                    file=uploaded_file,
                    owner=user,
                    folder=folder,
                    file_type=category,
                    extension=ext.strip('.'),
                    file_size=uploaded_file.size,
                    mime_type=uploaded_file.content_type or '',
                    checksum=checksum,
                    security_status=scan_result['status'],
                    risk_score=scan_result['risk_score'],
                    is_quarantined=scan_result['quarantine_required'],
                    quarantine_reason=scan_result['summary'],
                    security_summary=scan_result['summary'],
                )
                file_item.save()
                SentinelScan.objects.create(
                    file_item=file_item,
                    status=scan_result['status'],
                    risk_score=scan_result['risk_score'],
                    risk_level=scan_result['risk_level'],
                    summary=scan_result['summary'],
                    findings=scan_result['findings'],
                    recommendations=scan_result['recommendations'],
                    quarantine_required=scan_result['quarantine_required'],
                )

                # Generate thumbnail if image
                if category == 'image':
                    thumb = generate_image_thumbnail(file_item.file)
                    if thumb:
                        file_item.thumbnail.save(f"thumb_{file_item.id}.jpg", thumb, save=True)

                # Update user storage
                user.storage_used += uploaded_file.size
                user.save()

                created_file_items.append(file_item)

                ActivityLog.log_activity(
                    user=user,
                    action='UPLOAD',
                    details={'file_name': file_item.name, 'file_size': file_item.file_size, 'security_status': scan_result['status']},
                    ip_address=helper_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )

        serializer = FileItemSerializer(created_file_items, many=True)
        return Response({'message': 'Files uploaded successfully.', 'files': serializer.data}, status=status.HTTP_201_CREATED)


class FolderListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        name = request.data.get('name', '').strip()
        parent_id = request.data.get('parent_id')
        color = request.data.get('color', '#6366F1')

        if not name:
            return Response({'error': 'Folder name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        parent = None
        if parent_id:
            parent = get_object_or_404(Folder, id=parent_id, owner=request.user, is_trashed=False)

        folder = Folder.objects.create(
            name=name,
            owner=request.user,
            parent=parent,
            color=color
        )
        serializer = FolderSerializer(folder)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class FileItemDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        file_item = get_object_or_404(FileItem, id=pk, owner=request.user)
        # capture previous favorite state to detect changes
        previous_is_favorite = file_item.is_favorite

        name = request.data.get('name')
        folder_id = request.data.get('folder_id')
        is_favorite = request.data.get('is_favorite')
        tags = request.data.get('tags')

        if name:
            file_item.name = name.strip()
        if folder_id is not None:
            if folder_id == "":
                file_item.folder = None
            else:
                target_folder = get_object_or_404(Folder, id=folder_id, owner=request.user, is_trashed=False)
                file_item.folder = target_folder
        if is_favorite is not None:
            file_item.is_favorite = bool(is_favorite)
        if tags is not None:
            file_item.tags = tags

        file_item.save()
        # If favorite state changed, publish over channels so other open sessions update
        try:
            if is_favorite is not None and (bool(previous_is_favorite) != bool(file_item.is_favorite)):
                from asgiref.sync import async_to_sync
                from channels.layers import get_channel_layer
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(f'user_{request.user.id}', {
                        'type': 'activity',
                        'data': {
                            'event': 'favorite_update',
                            'file_id': file_item.id,
                            'is_favorite': bool(file_item.is_favorite)
                        }
                    })
        except Exception:
            pass
        serializer = FileItemSerializer(file_item)
        return Response(serializer.data)

    def delete(self, request, pk):
        item_type = request.query_params.get('type', 'file')
        permanent = request.query_params.get('permanent', 'false').lower() == 'true'

        if item_type == 'folder':
            folder = get_object_or_404(Folder, id=pk)
            # Owner always allowed
            if folder.owner == request.user:
                allowed = True
            else:
                # collaborator allowed to delete ONLY if folder is empty (no non-trashed files or subfolders)
                is_empty = (folder.files.filter(is_trashed=False).count() == 0) and (folder.subfolders.filter(is_trashed=False).count() == 0)
                allowed = is_empty and Collaborator.objects.filter(user=request.user, folder=folder, permission__in=['delete', 'edit']).exists()

            if not allowed:
                return Response({'error': 'Not authorized to delete this folder.'}, status=status.HTTP_403_FORBIDDEN)

            if permanent or folder.is_trashed:
                # permanently delete folder and files on disk
                for f in folder.files.all():
                    if f.file and os.path.exists(f.file.path):
                        try:
                            os.remove(f.file.path)
                        except Exception:
                            pass
                    f.delete()
                # delete subfolders
                for sub in folder.subfolders.all():
                    sub.delete()
                folder.delete()
                ActivityLog.log_activity(
                    user=request.user,
                    action='PERMANENT_DELETE',
                    details={'folder_name': folder.name},
                    ip_address=helper_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                return Response({'message': 'Folder deleted permanently.'}, status=status.HTTP_200_OK)
            else:
                folder.soft_delete()
                ActivityLog.log_activity(
                    user=request.user,
                    action='DELETE',
                    details={'folder_name': folder.name},
                    ip_address=helper_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                return Response({'message': 'Folder moved to trash.'}, status=status.HTTP_200_OK)

        # default: handle file
        file_item = get_object_or_404(FileItem, id=pk)
        # Permit owner or collaborator with delete/edit permission
        has_permission = (file_item.owner == request.user) or Collaborator.objects.filter(
            user=request.user, file_item=file_item, permission__in=['delete', 'edit']
        ).exists()
        if not has_permission:
            return Response({'error': 'Not authorized to delete this file.'}, status=status.HTTP_403_FORBIDDEN)

        if permanent or file_item.is_trashed:
            if file_item.file and os.path.exists(file_item.file.path):
                try:
                    os.remove(file_item.file.path)
                except Exception:
                    pass
            file_item.delete()
            ActivityLog.log_activity(
                user=request.user,
                action='PERMANENT_DELETE',
                details={'file_name': file_item.name},
                ip_address=helper_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            return Response({'message': 'File deleted permanently.'}, status=status.HTTP_200_OK)
        else:
            file_item.soft_delete()
            ActivityLog.log_activity(
                user=request.user,
                action='DELETE',
                details={'file_name': file_item.name},
                ip_address=helper_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            return Response({'message': 'File moved to trash.'}, status=status.HTTP_200_OK)


class RestoreItemAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        item_type = request.data.get('type', 'file')
        if item_type == 'folder':
            folder = get_object_or_404(Folder, id=pk)
            # Permit owner or collaborator with delete/edit permission for folder restore
            has_permission = (folder.owner == request.user) or Collaborator.objects.filter(
                user=request.user, folder=folder, permission__in=['delete', 'edit']
            ).exists()
            if not has_permission:
                return Response({'error': 'Not authorized to restore this folder.'}, status=status.HTTP_403_FORBIDDEN)
            folder.restore()
            ActivityLog.log_activity(user=request.user, action='RESTORE', details={'folder': folder.name})
        else:
            file_item = get_object_or_404(FileItem, id=pk)
            has_permission = (file_item.owner == request.user) or Collaborator.objects.filter(
                user=request.user, file_item=file_item, permission__in=['delete', 'edit']
            ).exists()
            if not has_permission:
                return Response({'error': 'Not authorized to restore this file.'}, status=status.HTTP_403_FORBIDDEN)
            file_item.restore()
            ActivityLog.log_activity(user=request.user, action='RESTORE', details={'file': file_item.name})
        return Response({'message': 'Item restored successfully.'})


class CompressZipAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        file_ids = request.data.get('file_ids', [])
        zip_name = request.data.get('zip_name', 'archive.zip')

        if not file_ids:
            return Response({'error': 'No files selected for compression.'}, status=status.HTTP_400_BAD_REQUEST)

        files = FileItem.objects.filter(id__in=file_ids, owner=request.user, is_trashed=False)
        zip_io = io.BytesIO()

        with zipfile.ZipFile(zip_io, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                if f.file and os.path.exists(f.file.path):
                    zf.write(f.file.path, arcname=f.name)

        zip_io.seek(0)
        zip_file = ContentFile(zip_io.getvalue(), name=zip_name)
        
        new_file = FileItem.objects.create(
            name=zip_name,
            original_name=zip_name,
            file=zip_file,
            owner=request.user,
            file_type='archive',
            extension='zip',
            file_size=zip_file.size,
            mime_type='application/zip',
            checksum=calculate_checksum(zip_file)
        )
        request.user.storage_used += zip_file.size
        request.user.save()

        serializer = FileItemSerializer(new_file)
        return Response({'message': 'ZIP archive created successfully.', 'file': serializer.data})
