# 02. HTTP Reporting

Dokumen ini menjelaskan mekanisme **HTTP-based reporting** dari edge box ke platform.
HTTP digunakan **hanya untuk reporting (push data)**, bukan untuk control.

Cakupan:
- Video upload
- Alarm / event reporting
- HTTP heartbeat
- Custom reporting (advanced)

---

## 2.1 Peran HTTP Reporting

HTTP Reporting dipakai untuk:

1. Upload artefak besar (video alarm)
2. Push hasil algoritma (alarm, counting, capture)
3. Alternatif heartbeat selain MQTT
4. Integrasi custom/proprietary protocol

Box = HTTP client  
Platform = HTTP server

---

## 2.2 Global Reporting Flow

```text
[Algorithm Triggered]
        |
        v
[Capture Image / Video]
        |
        +--> (optional) POST Video Upload
        |           |
        |           v
        |     [VideoId]
        |
        v
[Build Alarm JSON Payload]
        |
        v
POST Alarm Report Endpoint
        |
        v
[HTTP 200 => Success]
```

Aturan utama:
- Video harus diupload lebih dulu 
- VideoId dibawa di payload alarm 
- HTTP 200 dianggap sukses kecuali JSON Code != 0

---

## 2.3 Video Upload Interface
### 2.3.1 Fungsi
Mengirim file video alarm dan menerima **VideoId**.
---
### 2.3.2 Endpoint
```sh
POST <ServiceUploadURL>
Content-Type: multipart/form-data
```

URL dikonfigurasi di box:
```sh
Parameter Configuration -> ServiceUpload
```
---
### 2.3.3 Request Parameters (FORM-DATA)
|Field|Type|R0equired|Description|
|---|---|---|---|
|BoardIp| string | yes | IP box  |
|BoardId| string    | yes         | Unique device ID     |
|TaskSession| string| yes	| Task ID  |
|GBDeviceId| string| yes	| GB28181 device ID (boleh empty) |
|GBTaskChnId| string| yes	| GB channel ID (boleh empty)    |
|Video| file    | yes  | Video file     |
---
### 2.3.4 Response
```json
{
  "Result": {
    "Code": 0,
    "Desc": ""
  },
  "VideoId": "xxxxxxxxxxxx"
}
```
---
### 2.3.5 Error Handling
- HTTP != 200 → gagal 
- JSON invalid → gagal 
- Result.Code != 0 → gagal
---
## 2.4 Alarm / Event Reporting
### 2.4.1 Fungsi

Mengirim hasil algoritma (alarm / event) ke platform.

---
### 2.4.2 Endpoint
```sh
POST <MetadataUrl>
Content-Type: application/json
```
MetadataUrl ditentukan saat task configuration.
---
### 2.4.3 Reporting Rules
1. Video upload dilakukan sebelum alarm report 
2. Payload bersifat dynamic JSON 
3. Timestamp menggunakan microseconds 
4. Parsing server harus tolerant 
5. HTTP 200 dianggap sukses kecuali JSON Code != 0
---
### 2.4.4 Root Payload Structure
```json
{
  "BoardId": "string",
  "BoardIp": "string",
  "AlarmId": "uuid",
  "TaskSession": "string",
  "TaskDesc": "string",
  "Time": "YYYY-MM-DD HH:mm:ss",
  "TimeStamp": 1699426698084625,
  "VideoFile": "VideoId",
  "Media": {},
  "Result": {},
  "Summary": "string",
  "GPS": {},
  "Addition": {}
}
```
---
### 2.4.5 Media Object
```json
"Media": {
  "MediaName": "1",
  "MediaUrl": "rtsp://...",
  "MediaWidth": 1920,
  "MediaHeight": 1080,
  "GBTransport": false,
  "SubId": ""
}
```

Digunakan untuk:
- Mapping channel 
- Playback 
- Audit
---
### 2.4.6 Result Object (Algorithm Output)
```json
"Result": {
  "Type": "NoHelmet",
  "Description": "No helmet detected",
  "RelativeBox": [0.1, 0.2, 0.3, 0.4],
  "RelativeRegion": [],
  "Properties": []
}
```

RelativeBox
- Format: [x, y, width, height]
- Semua nilai percentage (0.0 - 1.0)

RelativeRegion 
- Polygon / trajectory 
- Dipakai untuk line crossing, flow counting, dll
---
### 2.4.7 Properties (Dynamic)
```json
"Properties": [
  {
    "property": "ParkingSec",
    "value": 60.19,
    "desc": "Parking duration",
    "display": "60.19 seconds"
  }
]
```

Catatan:
- Isi tergantung algoritma
- Tidak fixed schema
---
### 2.4.8 Image Fields
|Field	| Description                   |
|---|-------------------------------|
|ImageData	| Base64 JPEG (raw image)       |
|ImageDataLabeled	| Base64 JPEG (annotated image) |
|LocalRawPath	| Local path di box             |
|LocalLabeledPath	| Local path di box             |

Resolusi:
- Default: 640x360
- Bisa native camera resolution
---
### 2.4.9 Success Criteria
```json
{
  "Result": {
    "Code": 0,
    "Desc": ""
  }
}
```

- Code != 0 → dianggap gagal 
- HTTP 200 tanpa JSON → sukses
---
## 2.5 HTTP Heartbeat Reporting (Optional)

Alternatif MQTT heartbeat.

### 2.5.1 Endpoint
```sh
POST <RemoteInfoURL>
Content-Type: application/json
```

Dikonfigurasi di:
```sh
Parameter Configuration -> RemoteInfo
```
---
### 2.5.2 Payload
```json
{
  "MsgType": "Keepalive",
  "Info": {
    "BoardId": "...",
    "BoardIp": "...",
    "Status": "Online",
    "Version": "0.0.45",
    "Medias": [],
    "Tasks": [],
    "Time": 1690943852071
  }
}
```

Struktur Info identik dengan MQTT heartbeat.
---
## 2.6 Custom Reporting (Advanced)
### 2.6.1 Tujuan
Digunakan bila:
- Format proprietary
- Protocol non-HTTP
- Kebutuhan khusus client
---
## 2.6.2 Shared Library
Box akan mencoba load:
```sh
libAlarmReport.so
```
Symbol wajib:
```sh
api_result do_alarm_report(
    const std::string &url,
    const std::string &body
);
```
---
### 2.6.3 Flow
```text
[Alarm Generated]
      |
      v
[Check Custom Library]
      |
      +--> Exists -> Call do_alarm_report()
      |
      +--> Not Exists -> Default HTTP Reporting
```
---
### 2.6.4 Return Contract
```sh
struct api_result {
  int code;        // 0 = success
  char desc[256];
};
```
---
## 2.7 Troubleshooting Checklist
1. Video upload gagal
   - Cek ServiceUpload URL 
   - Cek DNS / Gateway
2. Alarm tidak muncul
   - Cek HTTP status 
   - Cek JSON Code
3. Image kosong 
   - Cek image type config
4. VideoId kosong
   - Upload step gagal
---
## 2.8 Dependency Summary
|Component|Required|
|-|-|
|Video Upload|Optional|
|Alarm Reporting|Required|
|HTTP Heartbeat|Optional|
|Custom Reporting|Optional|