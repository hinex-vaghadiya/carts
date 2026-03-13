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
            import json
            content = base64.b64decode(resp.json()['content']).decode('utf-8')
            backup_path = '/tmp/db_backup.json'
            
            data = json.loads(content)
            transactions = []
            deliveries = []
            txn_pk = 1
            del_pk = 1
            
            for item in data:
                if item['model'] == 'carts.order':
                    fields = item.get('fields', {})
                    order_pk = item['pk']
                    
                    stripe_id = fields.pop('stripe_session_id', None)
                    payment_date = fields.pop('payment_date', None)
                    del_date = fields.pop('delivery_date', None)
                    old_status = fields.get('status', 'PENDING')
                    amount = fields.get('total_amount', 0)
                    
                    if old_status in ['PAID', 'SHIPPED', 'DELIVERED']:
                        fields['status'] = 'CONFIRMED'
                        
                    if stripe_id or old_status != 'PENDING':
                        txn_status = 'SUCCESSFUL' if old_status != 'PENDING' else 'PENDING'
                        transactions.append({
                            'model': 'carts.transaction',
                            'pk': txn_pk,
                            'fields': {
                                'order': order_pk,
                                'stripe_session_id': stripe_id or f'migrated_{order_pk}',
                                'amount': amount,
                                'currency': 'inr',
                                'status': txn_status,
                                'created_at': payment_date or fields.get('created_at'),
                                'updated_at': payment_date or fields.get('created_at')
                            }
                        })
                        txn_pk += 1
                        
                    if old_status in ['SHIPPED', 'DELIVERED']:
                        del_status = 'DELIVERED' if old_status == 'DELIVERED' else 'DISPATCHED'
                        deliveries.append({
                            'model': 'carts.delivery',
                            'pk': del_pk,
                            'fields': {
                                'order': order_pk,
                                'status': del_status,
                                'dispatched_at': del_date or fields.get('created_at'),
                                'delivered_at': del_date if old_status == 'DELIVERED' else None
                            }
                        })
                        del_pk += 1
                        
            data.extend(transactions)
            data.extend(deliveries)
            
            with open(backup_path, 'w') as f:
                json.dump(data, f)
                
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