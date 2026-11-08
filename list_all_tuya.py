import sys
sys.path.append('/root/epaper-hub')
from integrations.tuya_client import fetch_all_tuya_devices, load_device_assignments

devs = fetch_all_tuya_devices()
assignments = load_device_assignments()

print(f"Total Tuya devices: {len(devs)}")
for d in devs:
    dev_id = d.get('id')
    name = d.get('name')
    online = d.get('online')
    category = d.get('category')
    assigned = assignments.get(dev_id, 'NO_ASSIGNED')
    status = d.get('status', [])
    print(f"ID: {dev_id} | Name: '{name}' | Cat: {category} | Online: {online} | Assigned: {assigned}")
