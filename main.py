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
semaphore = asyncio.Semaphore(10)

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

async def send_control_command(session, device_id, attribute, value, max_retries=3):
    data = {
        'attribute': attribute,
        'value': value
    }
    url = control_url(device_id)
    logger.info(f"Sending command to device {device_id}: {attribute} = {value}")
    async with semaphore:
        for attempt in range(max_retries):
            try:
                async with session.post(url, json=data, headers=headers, ssl=False, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"Successfully controlled device {device_id}")
                        return True
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for device {device_id}: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)  # 在重试之间添加短暂延迟
        logger.error(f'Failed to control device {device_id} after {max_retries} attempts')
    return False

async def get_device_state(session, device_id):
    url = f'http://{gateway_ip}/devices/{device_id}'
    try:
        async with session.get(url, headers=headers, ssl=False, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                if 'result' in data and 'status' in data['result']:
                    return data['result']['status']
    except Exception as e:
        logger.error(f"Error getting state for device {device_id}: {str(e)}")
    return None

async def control_devices(session, commands, batch_size=10):
    logger.info(f"Controlling {len(commands)} devices in batches of {batch_size}")
    start_time = time.time()
    all_results = []
    failed_commands = []
    
    for i in range(0, len(commands), batch_size):
        batch = commands[i:i+batch_size]
        tasks = [send_control_command(session, cmd['device_id'], cmd['attribute'], cmd['value']) for cmd in batch]
        batch_results = await asyncio.gather(*tasks)
        all_results.extend(batch_results)
        failed_commands.extend([cmd for cmd, result in zip(batch, batch_results) if not result])
    
    if failed_commands:
        logger.warning(f"Retrying {len(failed_commands)} failed commands")
        retry_results = await asyncio.gather(*[send_control_command(session, cmd['device_id'], cmd['attribute'], cmd['value'], max_retries=2) for cmd in failed_commands])
        all_results.extend(retry_results)
    
    end_time = time.time()
    execution_time = end_time - start_time
    success = all(all_results)
    logger.info(f"Control operation completed in {execution_time:.2f} seconds. Success: {success}")
    return success, execution_time

async def progressive_control(session, commands, batch_size=5, delay=1):
    logger.info(f"Starting progressive control for {len(commands)} commands")
    all_results = []
    for i in range(0, len(commands), batch_size):
        batch = commands[i:i+batch_size]
        success, _ = await control_devices(session, batch, batch_size)
        all_results.append(success)
        await asyncio.sleep(delay)  # 在批次之间添加延迟
    return all(all_results)

async def create_scene(session, scene_name, state):
    logger.info(f"Creating scene: {scene_name}")
    devices = await get_all_devices(session)
    if not devices:
        logger.error("Failed to get devices. Cannot create scene.")
        return False, 0
    
    commands = []
    for device in devices:
        device_id = device['id']
        device_type = device['type']
        
        if device_type in ['switch', 'dimmer']:
            current_state = await get_device_state(session, device_id)
            if current_state != state:
                commands.append({'device_id': device_id, 'attribute': 'status', 'value': state})
        
        if device_type == 'dimmer' and state:
            commands.append({'device_id': device_id, 'attribute': 'dimLevel', 'value': 100})
    
    start_time = time.time()
    success = await progressive_control(session, commands)
    end_time = time.time()
    execution_time = end_time - start_time
    
    verified = await verify_scene_state(session, state)
    logger.info(f"Scene {scene_name} creation completed. Success: {success and verified}")
    return success and verified, execution_time

async def verify_scene_state(session, expected_state):
    logger.info(f"Verifying scene state: expected {expected_state}")
    devices = await get_all_devices(session)
    all_correct = True
    for device in devices:
        device_id = device['id']
        device_type = device['type']
        if device_type in ['switch', 'dimmer']:
            current_state = await get_device_state(session, device_id)
            if current_state != expected_state:
                all_correct = False
                logger.warning(f"Device {device_id} state mismatch: current {current_state}, expected {expected_state}")
    logger.info(f"Scene state verification completed. All correct: {all_correct}")
    return all_correct

async def control_n_devices(session, scene_name, state, n):
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
    
    start_time = time.time()
    success = await progressive_control(session, commands)
    end_time = time.time()
    execution_time = end_time - start_time
    logger.info(f"Control of {n} devices completed. Success: {success}")
    return success, execution_time

async def main():
    async with ClientSession() as session:
        while True:
            print("\nPlease select an option:")
            print("0. Test Connection and Get All Devices")
            print("1. Turn All On")
            print("2. Turn All Off")
            print("3. Turn First 5 Devices On")
            print("4. Turn First 5 Devices Off")
            print("5. Turn First 10 Devices On")
            print("6. Turn First 10 Devices Off")
            print("7. Turn First 15 Devices On")
            print("8. Turn First 15 Devices Off")
            print("9. Turn First 20 Devices On")
            print("10. Turn First 20 Devices Off")
            print("11. Exit")
            
            choice = input("Enter your choice (0-11): ")
            
            if choice == '0':
                devices = await get_all_devices(session)
                print(f"Retrieved {len(devices)} devices")
            elif choice == '1':
                success, execution_time = await create_scene(session, "Turn All On", True)
                print(f"Turn All On completed in {execution_time:.2f} seconds. Success: {success}")
            elif choice == '2':
                success, execution_time = await create_scene(session, "Turn All Off", False)
                print(f"Turn All Off completed in {execution_time:.2f} seconds. Success: {success}")
            elif choice in ['3', '4', '5', '6', '7', '8', '9', '10']:
                n = [5, 5, 10, 10, 15, 15, 20, 20][int(choice) - 3]
                state = int(choice) % 2 == 1
                success, execution_time = await control_n_devices(session, f"Turn First {n} {'On' if state else 'Off'}", state, n)
                print(f"Turn First {n} {'On' if state else 'Off'} completed in {execution_time:.2f} seconds. Success: {success}")
            elif choice == '11':
                print("Exiting program")
                break
            else:
                print("Invalid option, please try again")

if __name__ == "__main__":
    asyncio.run(main())