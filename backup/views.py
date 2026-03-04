import os
import json
import base64
import requests
from io import StringIO
from datetime import datetime, timezone
from django.core.management import call_command
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

@csrf_exempt
@require_http_methods(["GET", "POST"])
def trigger_backup(request):
    """
    Endpoint to trigger a database backup.
    Exports app data as JSON and pushes it to GitHub.
    Protected by BACKUP_SECRET header or query param.
    """
    # 1. Validate secret
    backup_secret = os.environ.get("BACKUP_SECRET", "")
    provided_secret = request.headers.get("X-Backup-Secret", "") or request.GET.get("secret", "")
    
    if not backup_secret or provided_secret != backup_secret:
        return JsonResponse({"error": "Unauthorized"}, status=401)
        
    try:
        # 2. Run dumpdata for desired apps
        output = StringIO()
        call_command(
            "dumpdata",
            "carts", 
            "auth.user",
            "--indent",
            "2",
            "--natural-foreign",
            "--natural-primary",
            stdout=output,
        )
        json_data = output.getvalue()
        
        # 3. GitHub API Setup
        github_token = os.environ.get("GITHUB_TOKEN", "")
        # Expects format: username/repo
        github_repo = os.environ.get("GITHUB_REPO", "") 
        file_path = "backups/db_backup.json"
        
        if not github_token or not github_repo:
            return JsonResponse({"error": "GitHub credentials not configured"}, status=500)
            
        api_url = f"https://api.github.com/repos/{github_repo}/contents/{file_path}"
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        backup_branch = "backups"
        
        # 4. Ensure 'backups' branch exists, create from 'main' if not
        ref_url = f"https://api.github.com/repos/{github_repo}/git/ref/heads/{backup_branch}"
        ref_response = requests.get(ref_url, headers=headers)
        
        if ref_response.status_code == 404:
            main_ref_url = f"https://api.github.com/repos/{github_repo}/git/ref/heads/main"
            main_ref = requests.get(main_ref_url, headers=headers).json()
            main_sha = main_ref["object"]["sha"]
            
            create_ref_url = f"https://api.github.com/repos/{github_repo}/git/refs"
            requests.post(create_ref_url, headers=headers, json={
                "ref": f"refs/heads/{backup_branch}",
                "sha": main_sha,
            })
            
        # 5. Get existing file SHA on backups branch (needed for updates)
        sha = None
        get_response = requests.get(api_url, headers=headers, params={"ref": backup_branch})
        if get_response.status_code == 200:
            sha = get_response.json().get("sha")
            
        # 6. Encode content and define payload
        content_b64 = base64.b64encode(json_data.encode("utf-8")).decode("utf-8")
        payload = {
            "message": f"Automated daily DB backup - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "content": content_b64,
            "branch": backup_branch,
        }
        if sha:
            payload["sha"] = sha
            
        # 7. Push backup to branch
        put_response = requests.put(api_url, headers=headers, json=payload)
        
        if put_response.status_code in (200, 201):
            return JsonResponse({"success": True, "message": "Backup pushed to GitHub successfully"})
        else:
            return JsonResponse({"error": "Failed to push to GitHub", "details": put_response.json()}, status=500)
            
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
