import requests
import json

BASE_URL = 'http://127.0.0.1:8000'

def run_tests():
    print("==================================================")
    print("   CLOUDVAULT COMPREHENSIVE E2E SYSTEM TEST       ")
    print("==================================================")
    
    session = requests.Session()
    
    # 1. Test Unauthenticated Page Access & Auth Pages
    print("\n[1] Testing Public Auth Pages...")
    for path in ['/login/', '/accounts/login/', '/register/', '/accounts/register/', '/forgot-password/']:
        r = session.get(BASE_URL + path)
        assert r.status_code == 200, f"Failed {path}: {r.status_code}"
        print(f"  [OK] GET {path} -> 200 OK")

    # 2. Test User Registration via API & Session
    print("\n[2] Testing User Registration...")
    session = requests.Session()
    r = session.get(BASE_URL + '/register/')
    csrftoken = session.cookies.get('csrftoken')
    
    import time
    test_username = f"testuser_{int(time.time())}"
    test_password = "password123"
    
    reg_data = {
        'username': test_username,
        'email': f'{test_username}@cloudvault.io',
        'password': test_password,
        'password_confirm': test_password,
        'csrfmiddlewaretoken': csrftoken
    }
    r_reg = session.post(BASE_URL + '/register/', data=reg_data, headers={'Referer': BASE_URL + '/register/'})
    assert r_reg.status_code in [200, 302], f"Registration failed: {r_reg.status_code}"
    print(f"  [OK] User '{test_username}' registered successfully.")

    # 3. Test Dashboard & Authenticated Page Routes
    print("\n[3] Testing Authenticated Page Routes...")
    pages = ['/', '/files/', '/favorites/', '/shared/', '/trash/', '/analytics/']
    for p in pages:
        r = session.get(BASE_URL + p)
        assert r.status_code == 200, f"Failed page {p}: {r.status_code}"
        print(f"  [OK] GET {p} -> 200 OK")

    # 4. Test REST API Auth & JWT Token Obtaining
    print("\n[4] Testing JWT Authentication API...")
    token_resp = requests.post(BASE_URL + '/api/auth/token/', json={'username': test_username, 'password': test_password})
    assert token_resp.status_code == 200, f"Token failed: {token_resp.status_code}"
    tokens = token_resp.json()
    assert 'access' in tokens and 'refresh' in tokens
    print(f"  [OK] Obtained JWT Access & Refresh Tokens successfully.")
    
    jwt_headers = {'Authorization': f'Bearer {tokens["access"]}'}

    # 5. Test Folder Creation API
    print("\n[5] Testing Folder Creation API...")
    csrftoken = session.cookies.get('csrftoken')
    folder_resp = session.post(BASE_URL + '/api/folders/', json={
        'name': 'Test Project Folder',
        'color': '#8B5CF6'
    }, headers={'X-CSRFToken': csrftoken})
    assert folder_resp.status_code == 201, f"Folder creation failed: {folder_resp.status_code}"
    folder_data = folder_resp.json()
    folder_id = folder_data['id']
    print(f"  [OK] Folder '{folder_data['name']}' created (ID: {folder_id}).")

    # 6. Test Multi-File Upload API
    print("\n[6] Testing File Upload API...")
    files_to_upload = [
        ('files', ('document.txt', b'CloudVault Enterprise Storage Verification Test Document Content', 'text/plain')),
        ('files', ('sample_code.py', b'def hello():\n    print("Hello from CloudVault!")\n', 'text/x-python'))
    ]
    upload_resp = session.post(BASE_URL + '/api/files/upload/', files=files_to_upload, data={'folder_id': folder_id}, headers={'X-CSRFToken': csrftoken})
    assert upload_resp.status_code == 201, f"Upload failed: {upload_resp.status_code}"
    uploaded_files = upload_resp.json()['files']
    print(f"  [OK] Uploaded {len(uploaded_files)} files into folder ID {folder_id}.")

    file_doc_id = uploaded_files[0]['id']
    file_code_id = uploaded_files[1]['id']

    # 7. Test File Preview Content API
    print("\n[7] Testing File Preview API...")
    prev_resp = session.get(BASE_URL + f'/files/{file_code_id}/preview/')
    assert prev_resp.status_code == 200, f"Preview failed: {prev_resp.status_code}"
    prev_json = prev_resp.json()
    assert prev_json['type'] in ['code', 'text']
    print(f"  [OK] File preview returned content type '{prev_json['type']}'.")

    # 8. Test ZIP Archive Compression API
    print("\n[8] Testing ZIP Archive Compression API...")
    zip_resp = session.post(BASE_URL + '/api/files/compress/', json={
        'file_ids': [file_doc_id, file_code_id],
        'zip_name': 'project_files.zip'
    }, headers={'X-CSRFToken': csrftoken})
    assert zip_resp.status_code == 200, f"Zip compression failed: {zip_resp.status_code}"
    zip_file_data = zip_resp.json()['file']
    print(f"  [OK] ZIP archive '{zip_file_data['name']}' created successfully ({zip_file_data['formatted_size']}).")

    # 9. Test Share Link Generation (Password Protected + Expiry)
    print("\n[9] Testing File Sharing API (Password Protected)...")
    share_resp = session.post(BASE_URL + '/api/shares/', json={
        'file_id': file_doc_id,
        'access_type': 'public',
        'permission': 'view',
        'password': 'secretpassword',
        'expires_in_days': 7
    }, headers={'X-CSRFToken': csrftoken})
    assert share_resp.status_code == 201, f"Share link failed: {share_resp.status_code}"
    share_data = share_resp.json()
    share_token = share_data['token']
    print(f"  [OK] Password-protected share link generated (Token: {share_token}).")

    # 10. Test Public Share Link Portal Access with Password Prompt
    print("\n[10] Testing Password-Protected Share Portal Access...")
    pub_session = requests.Session()
    # Initial access should trigger password prompt
    r_pub = pub_session.get(BASE_URL + f'/s/{share_token}/')
    csrftoken_pub = pub_session.cookies.get('csrftoken')
    assert "Password Protected Link" in r_pub.text
    print("  [OK] Share portal correctly prompted for password.")

    # Submit wrong password
    r_wrong = pub_session.post(BASE_URL + f'/s/{share_token}/', data={'password': 'wrongpass', 'csrfmiddlewaretoken': csrftoken_pub}, headers={'Referer': BASE_URL + f'/s/{share_token}/'})
    assert "Incorrect password" in r_wrong.text
    print("  [OK] Incorrect password rejected.")

    # Submit correct password
    r_correct = pub_session.post(BASE_URL + f'/s/{share_token}/', data={'password': 'secretpassword', 'csrfmiddlewaretoken': csrftoken_pub}, headers={'Referer': BASE_URL + f'/s/{share_token}/'})
    assert r_correct.status_code in [200, 302]
    r_unlocked = pub_session.get(BASE_URL + f'/s/{share_token}/')
    assert "Download File Now" in r_unlocked.text
    print("  [OK] Correct password unlocked portal access.")

    # Download shared file
    r_dl = pub_session.get(BASE_URL + f'/s/{share_token}/download/')
    assert r_dl.status_code == 200
    print(f"  [OK] Shared file downloaded successfully (Size: {len(r_dl.content)} bytes).")

    # 11. Test Soft Delete & Trash Recovery
    print("\n[11] Testing Soft Delete & Trash Recovery...")
    r_trash = session.delete(BASE_URL + f'/api/files/{file_code_id}/', headers={'X-CSRFToken': csrftoken})
    assert r_trash.status_code == 200
    print("  [OK] File moved to Trash.")

    r_trash_page = session.get(BASE_URL + '/trash/')
    assert 'sample_code.py' in r_trash_page.text
    print("  [OK] File listed in Trash page.")

    r_restore = session.post(BASE_URL + f'/api/items/{file_code_id}/restore/', json={'type': 'file'}, headers={'X-CSRFToken': csrftoken})
    assert r_restore.status_code == 200
    print("  [OK] File restored from Trash successfully.")

    # 12. Test Admin Panel & User Management
    print("\n[12] Testing Admin Panel...")
    admin_session = requests.Session()
    admin_session.get(BASE_URL + '/login/')
    admin_csrf = admin_session.cookies.get('csrftoken')
    admin_session.post(BASE_URL + '/login/', data={'username': 'admin', 'password': 'admin123', 'csrfmiddlewaretoken': admin_csrf}, headers={'Referer': BASE_URL + '/login/'})
    
    r_admin = admin_session.get(BASE_URL + '/admin-panel/')
    assert r_admin.status_code == 200
    assert 'User Quota & Access Control' in r_admin.text
    print("  [OK] Admin Panel verified successfully.")

    print("\n==================================================")
    print("  ALL 12 END-TO-END VERIFICATION SUITES PASSED!   ")
    print("==================================================")

if __name__ == '__main__':
    run_tests()
