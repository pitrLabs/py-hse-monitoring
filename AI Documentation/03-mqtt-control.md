# 03. MQTT Control

Dokumen ini menjelaskan **kontrol dan manajemen perangkat via MQTT**.
MQTT digunakan untuk **command & control**, **query**, dan **status reporting**.
HTTP **tidak** digunakan untuk kontrol.

---

## 3.1 Peran MQTT dalam Sistem

MQTT dipakai untuk:

1. Konfigurasi device (media, task, parameter)
2. Kontrol lifecycle task (start / stop / delete)
3. Query status (media, task, capability)
4. Heartbeat & log reporting
5. Upgrade software

MQTT = **bidirectional control channel**

---

## 3.2 MQTT Connection
### 3.2.1 Transport
Didukung:
- TCP
- WebSocket

Contoh:
- tcp://192.168.0.1:1883
- ws://192.168.0.1:1883

Auth (optional):
###### tcp://username:password@192.168.0.1:1883

Dikonfigurasi di:
> Parameter Configuration -> RemoteBrokerUrl

---

## 3.3 Topic Convention
### 3.3.1 Control Topics

| Direction | Topic |
|---------|------|
| Platform → Box | `/edge_app_controller` |
| Box → Platform | `/edge_app_controller_reply` |
---
### 3.3.2 Reporting Topics

| Purpose | Topic |
|------|------|
| Heartbeat | `/board_ping` |
| Log | `/edge_app_notify` |

---

## 3.4 Common Message Structure
### 3.4.1 Control Message (Send)

```json
{
  "BoardId": "string",
  "Event": "/event_name",
  "...": "payload"
}
```
---
### 3.4.2 Reply Message
```json
{
  "BoardId": "string",
  "BoardIp": "string",
  "Event": "/event_name",
  "Result": {
    "Code": 0,
    "Desc": "Success"
  }
}
```

Aturan:
- Semua control wajib menyertakan BoardId
- Reply selalu dikirim ke <topic>_reply
---
## 3.5 Heartbeat Reporting
### 3.5.1 Topic
> /board_ping
---
### 3.5.2 Payload
```json
{
  "BoardId": "RJ-BOX-XXX",
  "BoardIp": "192.168.0.84",
  "Status": "Online",
  "Version": "0.0.45",
  "BoardTemp": "44(C)",
  "HostDisk": {
    "Total": 15913876,
    "Used": 3633824,
    "Available": 11588396
  },
  "HostMemory": [1300.5, 0.63],
  "Medias": [],
  "Tasks": [],
  "Time": 1690943852071
}
```

Interval default: 5 detik

---
## 3.6 Log Reporting
### 3.6.1 Topic
> /edge_app_notify
---
### 3.6.2 Payload
```json
{
  "BoardId": "RJ-BOX-XXX",
  "BoardIp": "192.168.0.84",
  "EventType": "/app_error_log",
  "Content": "Error detail message"
}
```

Digunakan untuk:
- Error
- Warning
- Runtime issue
---
## 3.7 Software Upgrade
### 3.7.1 Topic
Send:
>/edge_app_controller

Reply:
>/edge_app_controller_reply
---
### 3.7.2 Send Payload
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/app_upgrade_cmd",
  "Upgrade": {
    "file_url": "http://server/update.tar.gz",
    "file_name": "update.tar.gz",
    "md5": "32char_md5",
    "version": "0.0.46"
  }
}
```
---
### 3.7.3 Behavior
- Box download package
- Verify MD5
- Install
- Auto reboot
- Multiple reply possible (progress)
---
## 3.8 Schedule Template Management
### 3.8.1 Create Schedule
Event:
> /alg_schedule_create

Payload:
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_schedule_create",
  "name": "WorkHours",
  "summary": "Weekday only",
  "value": "336_bit_binary_string"
}
```
- 336 bit = 7 hari × 48 slot (30 menit)
---
### 3.8.2 Query Schedule
Event:
> /alg_schedule_fetch

Payload:
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_schedule_fetch"
}
```
---
## 3.9 Algorithm Capability Query
### 3.9.1 Purpose
Mengambil:
- Daftar algoritma
- Parameter
- Zone/line requirement
- Alarm types
---
### 3.9.2 Event
> /alg_ability_fetch

Payload:
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_ability_fetch"
}
```
---
## 3.10 Media Channel Management
### 3.10.1 Create / Update Media
Event:
> /alg_media_config

Payload:
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_media_config",
  "MediaName": "1",
  "MediaUrl": "rtsp://...",
  "MediaDesc": "Front Gate",
  "RtspTransport": false,
  "GBTransport": false
}
```
---
### 3.10.2 Delete Media
Event:
> /alg_media_delete

Payload:
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_media_delete",
  "MediaName": "1"
}
```
---
### 3.10.3 Query Media
Event:
> /alg_media_fetch

Payload:
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_media_fetch"
}
```
---
## 3.11 Algorithm Task Configuration
### 3.11.1 Create / Update Task
Event:
> /alg_task_config

Payload (simplified):
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_task_config",
  "AlgTaskSession": "task_1",
  "MediaName": "1",
  "AlgInfo": [1, 45],
  "MetadataUrl": "http://server/alarm",
  "ScheduleId": -1,
  "UserData": {
    "MethodConfig": [7]
  }
}
```
---
### 3.11.2 Task Control (Start / Stop)
Event:
> /alg_task_control

Payload:
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_task_control",
  "AlgTaskSession": "task_1",
  "Action": "start"
}
```

Action:
- start
- stop
---
### 3.11.3 Delete Task
Event:
> /alg_task_delete

Payload:
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_task_delete",
  "AlgTaskSession": "task_1"
}
```
---
### 3.11.4 Query Task
Event:
> /alg_task_fetch

Payload:
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_task_fetch"
}
```
---
## 3.12 Error Handling
|Code|Meaning|
|-|-|
|0|Success|
|!=0|Failed|

Platform harus membaca:
- HTTP/MQTT delivery
- Result.Code
- Result.Desc
---
## 3.13 MQTT Control Summary
|Area|MQTT|
|-|-|
|Media|Yes|
|Task|Yes|
|Schedule|Yes|
|Capability|Yes|
|Heartbeat|Yes|
|Upgrade|Yes|
|Alarm|No (HTTP)|