import aiohttp
import asyncio
import urllib3
from aiohttp import ClientSession
import nest_asyncio
import logging
import time

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

# Semaphore for limiting concurrent requests
semaphore = asyncio.Semaphore(20)  # 增加并发数量

async def get_all_devices(session):
    global device_cache
    if device_cache is not None:
        return device_cache
    
    url = f'http://{gateway_ip}/devices'
    try:
        async with session.get(url, headers=headers, ssl=False) as response:
            if response.status == 200:
                data = await response.json()
                if 'result' in data:
                    device_cache = data['result']
                    return device_cache
    except Exception as e:
        logger.error(f"Error getting devices: {str(e)}")
    return None

def control_url(device_id):
    return f'http://{gateway_ip}/devices/{device_id}/commands'

async def send_control_command_no_wait(session, device_id, attribute, value):
    data = {
        'attribute': attribute,
        'value': value
    }
    url = control_url(device_id)
    async with semaphore:
        try:
            await session.post(url, json=data, headers=headers, ssl=False)
            logger.info(f"Sent command to device {device_id}: {attribute} = {value}")
            return True
        except Exception as e:
            logger.error(f"Error sending command to device {device_id}: {str(e)}")
            return False

async def control_devices_no_wait(session, commands):
    # logger.info(f"Controlling {len(commands)} devices without waiting for responses")
    start_time = time.time()
    tasks = [send_control_command_no_wait(session, cmd['device_id'], cmd['attribute'], cmd['value']) for cmd in commands]
    results = await asyncio.gather(*tasks)
    end_time = time.time()
    execution_time = end_time - start_time
    success = all(results)
    logger.info(f"Control operation completed in {execution_time:.2f} seconds. All commands sent: {success}")
    return success, execution_time

async def control_n_devices_no_wait(session, scene_name, state, n):
    logger.info(f"Controlling first {n} devices: {scene_name}")
    devices = await get_all_devices(session)
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
    
    success, execution_time = await control_devices_no_wait(session, commands)
    logger.info(f"Control of {n} devices completed. All commands sent: {success}")
    return success, execution_time

async def main():
    async with ClientSession() as session:
        while True:
            print("\nPlease select an option:")
            print("0. Test Connection and Get All Devices")
            print("1. Turn All On (No Wait)")
            print("2. Turn All Off (No Wait)")
            print("3. Turn First 5 Devices On (No Wait)")
            print("4. Turn First 5 Devices Off (No Wait)")
            print("5. Turn First 10 Devices On (No Wait)")
            print("6. Turn First 10 Devices Off (No Wait)")
            print("7. Turn First 15 Devices On (No Wait)")
            print("8. Turn First 15 Devices Off (No Wait)")
            print("9. Turn First 20 Devices On (No Wait)")
            print("10. Turn First 20 Devices Off (No Wait)")
            print("11. Exit")
            
            choice = input("Enter your choice (0-11): ")
            
            if choice == '0':
                devices = await get_all_devices(session)
                print(f"Retrieved {len(devices)} devices")
            elif choice == '1':
                devices = await get_all_devices(session)
                success, execution_time = await control_n_devices_no_wait(session, "Turn All On", True, len(devices))
                print(f"Turn All On completed in {execution_time:.2f} seconds. All commands sent: {success}")
            elif choice == '2':
                devices = await get_all_devices(session)
                success, execution_time = await control_n_devices_no_wait(session, "Turn All Off", False, len(devices))
                print(f"Turn All Off completed in {execution_time:.2f} seconds. All commands sent: {success}")
            elif choice in ['3', '4', '5', '6', '7', '8', '9', '10']:
                n = [5, 5, 10, 10, 15, 15, 20, 20][int(choice) - 3]
                state = int(choice) % 2 == 1
                success, execution_time = await control_n_devices_no_wait(session, f"Turn First {n} {'On' if state else 'Off'}", state, n)
                print(f"Turn First {n} {'On' if state else 'Off'} completed in {execution_time:.2f} seconds. All commands sent: {success}")
            elif choice == '11':
                print("Exiting program")
                break
            else:
                print("Invalid option, please try again")

if __name__ == "__main__":
    asyncio.run(main())