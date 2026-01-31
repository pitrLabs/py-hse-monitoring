# 04. Algorithm Capability

Dokumen ini menjelaskan **mekanisme discovery dan deskripsi kemampuan algoritma**
yang tersedia di edge box melalui MQTT.

Algorithm capability digunakan oleh platform untuk:
- Mengetahui algoritma apa saja yang tersedia
- Menentukan parameter konfigurasi
- Menentukan kebutuhan zone / line
- Menentukan jenis alarm yang mungkin dihasilkan

---

## 4.1 Konsep Dasar

### 4.1.1 Definisi Algorithm Capability

Algorithm capability adalah **metadata algoritma** yang disediakan box, meliputi:
- ID algoritma
- Nama & deskripsi
- Parameter konfigurasi
- Kebutuhan region / line
- Jenis alarm (output)

Platform **tidak hardcode algoritma**, semua harus diambil dari capability API.

---

### 4.1.2 Primary Algorithm vs Sub Algorithm

Sistem mendukung **multi-stage algorithm**:

- **Primary algorithm**
  - Deteksi objek utama (misalnya: person, vehicle)
- **Sub algorithm**
  - Analisis lanjutan (helmet, mask, smoking, counting)

Contoh:
Person Detection (primary)
├─ No Helmet (sub)
├─ No Mask (sub)
├─ Smoking (sub)

---

## 4.2 Capability Query Flow

```text
[Platform]
    |
    | MQTT /alg_ability_fetch
    v
[Box]
    |
    | Reply with algorithm list
    v
[Platform renders UI dynamically]
```
---
## 4.3 MQTT Interface
### 4.3.1 Topic
Send:
>/edge_app_controller

Reply:
>/edge_app_controller_reply
---
### 4.3.2 Event
>/alg_ability_fetch
---
### 4.3.3 Request Payload
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_ability_fetch"
}
```
---
## 4.4 Response Structure
### 4.4.1 Root Response
```json
{
  "BoardId": "RJ-BOX-XXX",
  "BoardIp": "192.168.0.84",
  "Event": "/alg_ability_fetch",
  "Ability": [],
  "Result": {
    "Code": 0,
    "Desc": "Success"
  }
}
```
---
### 4.4.2 Ability Item Structure
```json
{
  "code": 1,
  "item": 207,
  "name": "Face Recognition",
  "desc": "Face recognition algorithm",
  "sub": true,
  "permitted": true,
  "attribute": {},
  "parameters": [],
  "policy": []
}
```
---
## 4.5 Algorithm Identification Fields
|Field|Description|
|-|-|
|code|Primary algorithm ID|
|item|Sub algorithm ID|
|name|Algorithm name|
|desc|Algorithm description|
|sub|Apakah sub-algorithm|
|permitted|Apakah diizinkan (license)|
---
## 4.6 Attribute: Zone / Line Requirement
```json
"attribute": {
  "zoneRequired": true,
  "zoneDesc": "Defines forbidden area",
  "lineRequired": false,
  "lineDesc": ""
}
```
---
### 4.6.1 zoneRequired
- true → wajib konfigurasi polygon
- false → tanpa region
---
### 4.6.2 lineRequired
- true → wajib konfigurasi line
- false → tidak perlu

Platform harus memaksa UI sesuai attribute ini.

---
## 4.7 Algorithm Parameters
### 4.7.1 Parameter Structure
```json
{
  "key": "parking_minute",
  "name": "Parking Duration",
  "class": "FLOAT",
  "type": 2,
  "required": true,
  "min": 0,
  "max": 60,
  "default": 5,
  "value": 5
}
```
---
### 4.7.2 Parameter Type Mapping
|class|type|Description|
|-|-|-|
|INTEGER|0|Integer|
|FLOAT|2|Float|
|BOOLEAN|4|Boolean|
|SELECTOR|5|Enum / option|
---
### 4.7.3 Selector Options
```json
"options": [
  {
    "key": "FaceRepo001",
    "name": "FaceRepo001 [1]",
    "value": 1,
    "enable": true
  }
]
```

Platform harus:
- Render dropdown
- Kirim value terpilih saat task config
---
## 4.8 Alarm Policy (Output Type)
```json
"policy": [
  {
    "property": "NoHelmet",
    "name": "No Helmet Detected"
  }
]
```

Digunakan untuk:
- Menentukan alarm type
- Mapping ke downstream system
---
## 4.9 Capability Usage in Task Configuration
### 4.9.1 Platform Flow
1. Query capability
2. User pilih algorithm
3. Platform render:
   - Parameter form 
   - Zone / line editor
4. Submit via /alg_task_config
---
### 4.9.2 Validation Rules
Platform WAJIB memastikan:
- Semua required parameter terisi
- Zone / line sesuai attribute
- Algorithm permitted == true
---
## 4.10 Example Capability Item (Full)
```json
{
  "code": 52,
  "item": 207,
  "name": "Face Recognition",
  "desc": "Face recognition algorithm",
  "sub": true,
  "permitted": true,
  "attribute": {
    "zoneRequired": false,
    "lineRequired": false,
    "zoneDesc": "",
    "lineDesc": ""
  },
  "parameters": [
    {
      "key": "face_reg_similarity",
      "name": "Similarity Threshold",
      "class": "FLOAT",
      "type": 2,
      "min": 0.35,
      "max": 1.0,
      "required": true,
      "default": 0.4,
      "value": 0.4
    }
  ],
  "policy": [
    {
      "property": "FaceId",
      "name": "Registered Face Detected"
    },
    {
      "property": "Stranger",
      "name": "Unregistered Face"
    }
  ]
}
```
---
## 4.11 Error Handling
Jika query gagal:
```json
{
  "Result": {
    "Code": 1001,
    "Desc": "Not authorized"
  }
}
```

Platform tidak boleh mengasumsikan algoritma tersedia.

---
## 4.12 Summary
|Item|Description|
|-|-|
|Capability|Metadata algoritma|
|Source|MQTT|
|UI Driven|Yes|
|Hardcode|Forbidden|
|Dependency|Task Config|