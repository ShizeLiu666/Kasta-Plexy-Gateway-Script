import aiohttp
import asyncio
import urllib3
from aiohttp import ClientSession
import nest_asyncio
import logging
import time
from multiprocessing import Pool, cpu_count

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Apply nest_asyncio to allow asyncio in Jupyter
nest_asyncio.apply()

# Disable insecure request warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Basic configuration
gateway_ip = '192.168.0.109'
network_pin = '13579246'
headers = {
    'Authorization': f'Bearer {network_pin}',
    'Content-Type': 'application/json',
    'User-Agent': 'PostmanRuntime/7.42.0',
    'Accept': '*/*',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive'
}

# Cache for storing device information
device_cache = None

def get_all_devices():
    global device_cache
    if device_cache is not None:
        return device_cache
    
    import requests
    url = f'http://{gateway_ip}/devices'
    try:
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code == 200:
            data = response.json()
            if 'result' in data:
                device_cache = data['result']
                return device_cache
    except Exception as e:
        logger.error(f"Error getting devices: {str(e)}")
    return None

def control_url(device_id):
    return f'http://{gateway_ip}/devices/{device_id}/commands'

def send_control_command(args):
    device_id, attribute, value = args
    import requests
    data = {
        'attribute': attribute,
        'value': value
    }
    url = control_url(device_id)
    try:
        response = requests.post(url, json=data, headers=headers, verify=False)
        logger.info(f"Sent command to device {device_id}: {attribute} = {value}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error sending command to device {device_id}: {str(e)}")
        return False

def control_devices_parallel(commands, num_processes=None):
    if num_processes is None:
        num_processes = min(cpu_count(), len(commands))
    
    logger.info(f"Controlling {len(commands)} devices using {num_processes} processes")
    start_time = time.time()
    
    with Pool(num_processes) as pool:
        results = pool.map(send_control_command, [(cmd['device_id'], cmd['attribute'], cmd['value']) for cmd in commands])
    
    end_time = time.time()
    execution_time = end_time - start_time
    success = all(results)
    logger.info(f"Control operation completed in {execution_time:.2f} seconds. All commands sent: {success}")
    return success, execution_time

def create_scene_parallel(scene_name, state):
    logger.info(f"Creating scene: {scene_name}")
    devices = get_all_devices()
    if not devices:
        logger.error("Failed to get devices. Cannot create scene.")
        return False, 0
    
    commands = []
    for device in devices:
        device_id = device['id']
        device_type = device['type']
        
        if device_type in ['switch', 'dimmer']:
            commands.append({'device_id': device_id, 'attribute': 'status', 'value': state})
        
        if device_type == 'dimmer' and state:
            commands.append({'device_id': device_id, 'attribute': 'dimLevel', 'value': 100})
    
    return control_devices_parallel(commands)

def control_n_devices_parallel(scene_name, state, n):
    logger.info(f"Controlling first {n} devices: {scene_name}")
    devices = get_all_devices()
    if not devices:
        logger.error("Failed to get devices. Cannot control devices.")
        return False, 0
    
    devices = devices[:n]
    
    commands = []
    for device in devices:
        device_id = device['id']
        device_type = device['type']
        
        if device_type in ['switch', 'dimmer']:
            commands.append({'device_id': device_id, 'attribute': 'status', 'value': state})
        
        if device_type == 'dimmer' and state:
            commands.append({'device_id': device_id, 'attribute': 'dimLevel', 'value': 100})
    
    return control_devices_parallel(commands)

def main():
    while True:
        print("\nPlease select an option:")
        print("0. Test Connection and Get All Devices")
        print("1. Turn All On (Parallel)")
        print("2. Turn All Off (Parallel)")
        print("3. Turn First 5 Devices On (Parallel)")
        print("4. Turn First 5 Devices Off (Parallel)")
        print("5. Turn First 10 Devices On (Parallel)")
        print("6. Turn First 10 Devices Off (Parallel)")
        print("7. Turn First 15 Devices On (Parallel)")
        print("8. Turn First 15 Devices Off (Parallel)")
        print("9. Turn First 20 Devices On (Parallel)")
        print("10. Turn First 20 Devices Off (Parallel)")
        print("11. Exit")
        
        choice = input("Enter your choice (0-11): ")
        
        if choice == '0':
            devices = get_all_devices()
            print(f"Retrieved {len(devices)} devices")
        elif choice == '1':
            success, execution_time = create_scene_parallel("Turn All On", True)
            print(f"Turn All On completed in {execution_time:.2f} seconds. All commands sent: {success}")
        elif choice == '2':
            success, execution_time = create_scene_parallel("Turn All Off", False)
            print(f"Turn All Off completed in {execution_time:.2f} seconds. All commands sent: {success}")
        elif choice in ['3', '4', '5', '6', '7', '8', '9', '10']:
            n = [5, 5, 10, 10, 15, 15, 20, 20][int(choice) - 3]
            state = int(choice) % 2 == 1
            success, execution_time = control_n_devices_parallel(f"Turn First {n} {'On' if state else 'Off'}", state, n)
            print(f"Turn First {n} {'On' if state else 'Off'} completed in {execution_time:.2f} seconds. All commands sent: {success}")
        elif choice == '11':
            print("Exiting program")
            break
        else:
            print("Invalid option, please try again")

if __name__ == "__main__":
    main()