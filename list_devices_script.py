import sys
sys.path.append('/root/epaper-hub')
import database

states = database.get_all_device_states()
print("Total devices:", len(states))
for s in states:
    print(dict(s))
