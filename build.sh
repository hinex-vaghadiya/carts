pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
# Auto-restore logic: Detect fresh DB and restore from GitHub backups branch
python -c "
import django, os, sys, requests, json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from carts.models import Cart
# Check if DB is empty
if Cart.objects.count() == 0:
    github_token = os.environ.get('GITHUB_TOKEN', '')
    github_repo = os.environ.get('GITHUB_REPO', '')
    
    if github_token and github_repo:
        print('Fresh DB detected. Fetching backup from GitHub...')
        api_url = f'https://api.github.com/repos/{github_repo}/contents/backups/db_backup.json'
        headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
        resp = requests.get(api_url, headers=headers, params={'ref': 'backups'})
        
        if resp.status_code == 200:
            import base64
            content = base64.b64decode(resp.json()['content']).decode('utf-8')
            backup_path = '/tmp/db_backup.json'
            
            with open(backup_path, 'w') as f:
                f.write(content)
                
            from django.core.management import call_command
            call_command('loaddata', backup_path)
            print('Backup restored successfully!')
        else:
            print('No backup found on GitHub backups branch.')
    else:
        print('Fresh DB detected but GitHub credentials not set. Cannot restore.')
else:
    print('DB already has data. Skipping restore.')
"