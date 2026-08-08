import os
import hashlib
import zipfile
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile

def detect_file_category(extension, mime_type=''):
    ext = extension.lower().strip('.')
    images = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'tiff', 'ico'}
    videos = {'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v', '3gp'}
    audios = {'mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'wma'}
    pdfs = {'pdf'}
    documents = {'doc', 'docx', 'odt', 'rtf', 'txt'}
    spreadsheets = {'xls', 'xlsx', 'csv', 'ods'}
    presentations = {'ppt', 'pptx', 'odp'}
    archives = {'zip', 'rar', '7z', 'tar', 'gz', 'bz2'}
    codes = {'py', 'js', 'html', 'css', 'json', 'xml', 'c', 'cpp', 'java', 'php', 'rb', 'go', 'rs', 'ts', 'sh', 'sql', 'md'}

    if ext in images or 'image' in mime_type:
        return 'image'
    elif ext in videos or 'video' in mime_type:
        return 'video'
    elif ext in audios or 'audio' in mime_type:
        return 'audio'
    elif ext in pdfs or 'pdf' in mime_type:
        return 'pdf'
    elif ext in spreadsheets or 'spreadsheet' in mime_type or 'excel' in mime_type or 'csv' in mime_type:
        return 'spreadsheet'
    elif ext in presentations or 'presentation' in mime_type or 'powerpoint' in mime_type:
        return 'presentation'
    elif ext in documents or 'word' in mime_type or 'document' in mime_type:
        return 'document'
    elif ext in archives or 'zip' in mime_type or 'compressed' in mime_type:
        return 'archive'
    elif ext in codes:
        return 'code'
    elif ext == 'txt':
        return 'text'
    return 'other'

def get_file_icon_class(file_type, extension=''):
    mapping = {
        'image': 'bi-file-earmark-image text-purple',
        'video': 'bi-file-earmark-play text-danger',
        'audio': 'bi-file-earmark-music text-info',
        'pdf': 'bi-file-earmark-pdf text-danger',
        'document': 'bi-file-earmark-word text-primary',
        'spreadsheet': 'bi-file-earmark-excel text-success',
        'presentation': 'bi-file-earmark-ppt text-warning',
        'archive': 'bi-file-earmark-zip text-secondary',
        'code': 'bi-file-earmark-code text-cyan',
        'text': 'bi-file-earmark-text text-muted',
        'other': 'bi-file-earmark text-secondary',
    }
    return mapping.get(file_type, 'bi-file-earmark text-secondary')

def calculate_checksum(file_obj):
    sha256_hash = hashlib.sha256()
    file_obj.seek(0)
    for chunk in iter(lambda: file_obj.read(4096), b""):
        sha256_hash.update(chunk)
    file_obj.seek(0)
    return sha256_hash.hexdigest()

def generate_image_thumbnail(file_obj, max_size=(300, 300)):
    try:
        file_obj.seek(0)
        image = Image.open(file_obj)
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save as JPEG thumbnail
        thumb_io = BytesIO()
        if image.mode != 'RGB':
            image = image.convert('RGB')
        image.save(thumb_io, format='JPEG', quality=85)
        thumb_file = ContentFile(thumb_io.getvalue())
        return thumb_file
    except Exception as e:
        print(f"Thumbnail generation error: {e}")
        return None

def format_bytes(size):
    if not size:
        return "0 B"
    size = float(size)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"
