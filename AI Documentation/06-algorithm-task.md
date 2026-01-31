# 06. Algorithm Task

Dokumen ini menjelaskan **konfigurasi, struktur, dan lifecycle Algorithm Task**.
Algorithm Task adalah **binding antara algorithm + media channel + rule + parameter**
yang dieksekusi oleh edge box.

Task adalah **unit eksekusi utama** dalam sistem.

---

## 6.1 Konsep Dasar

### 6.1.1 Definisi Algorithm Task

Algorithm Task merepresentasikan:
- Media channel yang dianalisis
- Algorithm (primary + sub)
- Parameter algoritma
- Rule (zone / line / region)
- Endpoint reporting (HTTP)

Tanpa task:
- Algorithm **tidak berjalan**
- Tidak ada alarm / event

---

### 6.1.2 Relasi Task

```text
Media Channel
      |
      v
Algorithm Task
      |
      v
HTTP Alarm Reporting
```
---

## 6.2 Task Lifecycle
```text
Create -> Auto Start -> Running
           |               |
           |               v
           +----------> Stop
                            |
                            v
                          Delete
```

Aturan:
- Task auto start setelah create
- Task harus stop sebelum delete
---
## 6.3 MQTT Interface
### 6.3.1 Topic

Send:
> /edge_app_controller

Reply:
> /edge_app_controller_reply
---
## 6.4 Create / Update Algorithm Task
### 6.4.1 Event
> /alg_task_config

Event yang sama digunakan untuk:
- Create
- Update

Ditentukan dari apakah AlgTaskSession sudah ada.

---
### 6.4.2 Request Payload (Full)
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_task_config",
  "AlgTaskSession": "task_001",
  "TaskDesc": "Helmet detection front gate",
  "MediaName": "1",
  "MetadataUrl": "http://server/alarm/report",
  "ScheduleId": -1,
  "AlgInfo": [1, 45],
  "RuleProperty": [],
  "UserData": {}
}
```
---
### 6.4.3 Core Fields Description
|Field|Required|Description|
|-|-|-|
|AlgTaskSession|yes|Task unique ID|
|MediaName|yes|Media channel|
|AlgInfo|yes|Algorithm list|
|MetadataUrl|yes|Alarm reporting endpoint|
|ScheduleId|optional|Schedule template|
|RuleProperty|optional|Zone / line|
|UserData|yes|Algorithm parameters|
---
## 6.5 AlgInfo (Algorithm Binding)
> "AlgInfo": [1, 45]

Makna:
- Primary algorithm ID
- Sub algorithm ID(s)

Mapping harus berasal dari:
> /alg_ability_fetch
---
## 6.6 RuleProperty (Zone / Line / Region)
RuleProperty digunakan untuk:
- Forbidden area
- Detection zone
- Line crossing
- Post area
---
### 6.6.1 RuleProperty Structure
```json
{
  "RuleId": "zone_1",
  "RuleType": 0,
  "Algo": {
    "majorId": 1,
    "minorId": 7
  },
  "Points": [
    { "X": 0.1, "Y": 0.2 },
    { "X": 0.3, "Y": 0.2 },
    { "X": 0.3, "Y": 0.5 }
  ]
}
```
---
### 6.6.2 RuleType Mapping
|RuleType|Meaning|
|-|-|
|0|Detection Region|
|1|Forbidden Area|
|2|Auxiliary Line|
|4|Dedicated Algorithm Zone|
---
### 6.6.3 Points Rules
|Shape|Minimum Points|
|-|-|
|Polygon|3|
|Line|2|

Semua koordinat:
- Percentage (0.0 – 1.0)
- Relative ke frame
---
## 6.7 UserData (Algorithm Parameters)
### 6.7.1 Purpose
Menampung:
- Parameter algoritma
- Config tambahan
- Algorithm-specific flags
---
### 6.7.2 Structure
```json
"UserData": {
  "MethodConfig": [7],
  "staff_sec": 8,
  "staff_number": 1,
  "staff_repeat_alarm_sec": 8
}
```
Parameter harus sesuai capability:
- Key
- Type
- Required
---
## 6.8 Schedule Binding
> "ScheduleId": -1

| Value   |Meaning|
|---------|-|
| **-1**  |Always on|
| **>=0** |Custom schedule|

Schedule dibuat via:
> /alg_schedule_create
---
## 6.9 Task Auto Behavior
|Event|Behavior|
|-|-|
|Create|Auto start|
|Update|Auto restart|
|Media update|Task restart|
|Schedule inactive|Task paused|
---
## 6.10 Task Control (Start / Stop)
### 6.10.1 Event
> /alg_task_control
---
### 6.10.2 Payload
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_task_control",
  "AlgTaskSession": "task_001",
  "Action": "stop"
}
```
Action:
- start
- stop
---
## 6.11 Delete Task
### 6.11.1 Event
> /alg_task_delete
---
### 6.11.2 Payload
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_task_delete",
  "AlgTaskSession": "task_001"
}
```

Aturan:
- Task harus stop
- Delete task hapus semua state
---
## 6.12 Query Task
### 6.12.1 Event
> /alg_task_fetch
---
### 6.12.2 Payload
```json
{
  "BoardId": "RJ-BOX-XXX",
  "Event": "/alg_task_fetch"
}
```
---
### 6.12.3 Response (Simplified)
```json
{
  "Content": [
    {
      "AlgTaskSession": "task_001",
      "MediaName": "1",
      "Status": "Running",
      "AlgInfo": [1, 45]
    }
  ],
  "Result": {
    "Code": 0,
    "Desc": "Success"
  }
}
```
---
### 6.13 Validation Rules (Platform Side)
Platform WAJIB memastikan:
1. Media channel valid & normal
2. Algorithm permitted
3. Required parameter terisi
4. Zone / line sesuai attribute
5. MetadataUrl reachable
---
## 6.14 Common Failure Cases
|Case|Cause|
|-|-|
|Task not running|Media error|
|No alarm|MetadataUrl invalid|
|Wrong detection|Wrong zone|
|Task rejected|Missing required param|
---
## 6.15 Dependency Summary
|Component|Dependency|
|-|-|
|Task|Media + Capability|
|Alarm|Task|
|Schedule|Optional|
|MQTT|Mandatory|