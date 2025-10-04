import requests
import time
controller_ip = 'http://icicle-ct1.local:8080'

# ===== Step 1 =====
# response = requests.get(f'{controller_ip}/health')
# print(response.json())


# ===== Step 2 =====
# response = requests.post(f'{controller_ip}/startup',json={}, headers={'Content-Type': 'application/json'})
# print(response.text)
# print(response.status_code)
# time.sleep(20)
# response = requests.get(f'{controller_ip}/health')
# print(response.json())


# ===== Step 3 =====
# payload = {
#     "gpu": "false",
#     "ckn_mqtt_broker": "192.168.0.122",
#     "ct_version": "test",
#     "mode": "demo",
#     "min_seconds_between_images":"5",
#     "model": "yolov5nu_ep120_bs32_lr0.001_0cfb1c03.pt",
#     "inference_server": "false",
#     "detection_thresholds": "{\"animal\": \"0.4\", \"image_store_save_threshold\": \"0\", \"image_store_reduce_save_threshold\": \"0\"}"
# }
# response = requests.post(f'{controller_ip}/configure', json=payload)
# print(response.json())
# time.sleep(20)
# response = requests.get(f'{controller_ip}/health')
# print(response.json())


# ===== Step 4 =====
response = requests.post(f'{controller_ip}/run')
print(response.json())
time.sleep(70)
response = requests.get(f'{controller_ip}/health')
print(response.json())


# ===== Step 5 =====
# response = requests.post(f'{controller_ip}/stop')
# print(response.json())
# time.sleep(20)
# response = requests.get(f'{controller_ip}/health')
# print(response.json())

# response = requests.get(f'{controller_ip}/controller_logs/download')
# print(response.content.decode('utf-8'))