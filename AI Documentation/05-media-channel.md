# 05. Media Channel

Dokumen ini menjelaskan **manajemen media channel (video stream)** pada edge box.
Media channel adalah **sumber input video** yang akan dipakai oleh algorithm task.

Media channel **wajib dikonfigurasi sebelum task dibuat**.

---

## 5.1 Konsep Dasar

### 5.1.1 Definisi Media Channel

Media channel merepresentasikan:
- 1 stream video
- 1 sumber RTSP
- 1 logical channel di box

Karakteristik:
- Protocol: **RTSP**
- Codec: **H.264 / H.265**
- Resolution: **720p / 1080p**
- Jumlah channel tergantung hardware (umumnya 9 / 16)

---

### 5.1.2 Relasi Media Channel

```text
Media Channel
      |
      v
Algorithm Task
      |
      v
HTTP Alarm Reporting
```
Satu media channel:
- Bisa dipakai lebih dari satu task
- Tidak bisa dihapus jika masih dipakai task
---
## 5.2 Media Channel Lifecycle
> Create -> Update -> In Use -> (Optional Update) -> Delete


Aturan:
- Delete hanya boleh jika tidak ada task aktif
- Update RTSP akan restart stream internal
---
## 5.3 MQTT Interface
### 5.3.1 Topic

Send:
> /edge_app_controller

Reply:
> /edge_app_controller_reply
---
## 5.4 Create / Update Media Channel
### 5.4.1 Event
> /alg_media_config

Event yang sama dipakai untuk:
- Create
- Update

Ditentukan dari apakah MediaName sudah ada atau belum.

---
### 5.4.2 Request Payload
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_media_config",
  "MediaName": "1",
  "MediaUrl": "rtsp://user:pass@192.168.0.10/stream1",
  "MediaDesc": "Front Gate Camera",
  "RtspTransport": false,
  "GBTransport": false,
  "SubId": ""
}
```
---
### 5.4.3 Request Field Description
|Field|Required|Description|
|-|-|-|
|BoardId|yes|Unique box ID|
|Event|yes|/alg_media_config|
|MediaName|yes|Channel identifier|
|MediaUrl|yes|RTSP URL|
|MediaDesc|optional|Alias / label|
|RtspTransport|optional|Enable RTSP proxy|
|GBTransport|optional|Enable GB28181 forwarding|
|SubId|optional|GB channel ID (required if GBTransport=true)|

---
### 5.4.4 Response
```json
{
  "BoardId": "RJ-BOX-XXX",
  "BoardIp": "192.168.0.11",
  "Event": "/alg_media_config",
  "MediaName": "1",
  "Result": {
    "Code": 0,
    "Desc": "Saved"
  }
}
```
---
## 5.5 Delete Media Channel
### 5.5.1 Event
> /alg_media_delete
---
### 5.5.2 Request Payload
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_media_delete",
  "MediaName": "1"
}
```
---
### 5.5.3 Delete Rules
- Media tidak boleh dipakai task
- Jika masih dipakai → error
---
### 5.5.4 Response
```json
{
  "BoardId": "RJ-BOX-XXX",
  "BoardIp": "192.168.0.11",
  "Event": "/alg_media_delete",
  "MediaName": "1",
  "Result": {
    "Code": 0,
    "Desc": "Deleted"
  }
}
```
---
## 5.6 Query Media Channels
### 5.6.1 Event
> /alg_media_fetch
---
### 5.6.2 Request Payload
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_media_fetch"
}
```
---
### 5.6.3 Response Payload
```json
{
  "BoardId": "RJ-BOX-XXX",
  "BoardIp": "192.168.0.11",
  "Event": "/alg_media_fetch",
  "Content": [
    {
      "MediaName": "1",
      "MediaDesc": "Front Gate",
      "MediaUrl": "rtsp://...",
      "RtspTransport": false,
      "GBTransport": false,
      "SubId": "",
      "MediaStatus": {
        "type": 4,
        "style": "success",
        "label": "Normal"
      }
    }
  ],
  "Result": {
    "Code": 0,
    "Desc": "Success"
  }
}
```
---
## 5.7 Media Status
### 5.7.1 Status Type Mapping
|type|Meaning|
|-|-|
|0|Unknown|
|1|Initializing|
|2|Warning|
|3|Error|
|4|Normal|
---
### 5.7.2 Status Usage
Platform harus:
- Menampilkan status realtime
- Mencegah task creation jika status Error
---
## 5.8 RTSP Proxy & GB28181
### 5.8.1 RtspTransport
Jika true:
- Box expose stream ulang
- URL:
    > rtsp://<box_ip>/channel/<MediaName>
---
### 5.8.2 GBTransport
Jika true:
- Stream diteruskan ke platform GB28181
- SubId wajib diisi
---
## 5.9 Media Channel Validation Rules
Platform WAJIB memastikan:
- MediaUrl valid RTSP
- MediaName unik
- SubId ada jika GBTransport=true
- Media status normal sebelum task dibuat
---
## 5.10 Dependency Summary
|Component|Depends On Media|
|-|-|
|Algorithm Task|Yes|
|Alarm Reporting|Yes|
|Capability|No|
|Schedule|No|
---
## 5.11 Common Failure Cases
|Case|Cause|
|-|-|
|Stream Error|RTSP unreachable|
|Cannot delete|Media in use|
|No video|Codec unsupported|
|Delay|Network latency|