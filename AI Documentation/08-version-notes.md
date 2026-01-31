# 08. Version Notes

Dokumen ini mencatat **perubahan perilaku sistem, fitur, dan kompatibilitas**
antar versi firmware / SDK edge box.

Version Notes **WAJIB dijadikan referensi** oleh platform untuk:
- Menentukan feature availability
- Menentukan fallback behavior
- Menghindari hard dependency pada versi tertentu

---

## 8.1 Versioning Policy
### 8.1.1 Format Versi

MAJOR.MINOR.PATCH

Contoh:
> 0.0.37

Makna:
- MAJOR: perubahan arsitektur besar (jarang)
- MINOR: fitur baru / breaking behavior
- PATCH: bugfix / optimization

---

## 8.2 Feature Timeline Summary

| Version | Key Changes |
|------|------------|
| 0.0.1 | Initial release |
| 0.0.6 | HTTP reporting support |
| 0.0.12 | SDK encapsulation |
| 0.0.14 | GPS support |
| 0.0.15 | Task scheduling |
| 0.0.16 | Schedule template |
| 0.0.17 | BM1684 platform |
| 0.0.20 | Polygon region |
| 0.0.21 | PPE detection |
| 0.0.24 | Bugfix |
| 0.0.29 | HDMI output |
| 0.0.31 | Video output optimization |
| 0.0.37 | Custom reporting hook |
| 0.0.43 | HTTP heartbeat |
| 0.0.46 | Extended heartbeat info |

---

## 8.3 Reporting Related Changes

### 8.3.1 Alarm Reporting ACK (>= 0.0.37)

Behavior:
- Alarm reporting response **dibaca**
- JSON `Result.Code != 0` dianggap failure
- Sebelumnya: HTTP 200 selalu sukses

Impact:
- Platform harus parse response body

---

### 8.3.2 Custom Alarm Reporting (>= 0.0.37)

Fitur:
- `libAlarmReport.so`
- Override default HTTP reporting

Fallback:
- Jika library tidak ada / error → default HTTP

---

## 8.4 Heartbeat Changes

### 8.4.1 MQTT Heartbeat (All Versions)

- Topic: `/board_ping`
- Interval default: 5s

---

### 8.4.2 HTTP Heartbeat (>= 0.0.43)

- Endpoint configurable via `RemoteInfo`
- Payload identik dengan MQTT heartbeat
- Digunakan jika MQTT tidak tersedia

---

## 8.5 Media & Stream Changes

### 8.5.1 RTSP Proxy

| Version | Behavior |
|------|---------|
| < 0.0.29 | Limited |
| >= 0.0.29 | Stable proxy |

---

### 8.5.2 GB28181 Support

| Version | Notes |
|------|------|
| 0.0.15 | Initial uplink |
| >= 0.0.46 | SubId in heartbeat |

---

## 8.6 Algorithm Capability Changes

### 8.6.1 Polygon Support (>= 0.0.20)

- Region bisa polygon
- RuleProperty.Points >= 3

---

### 8.6.2 Properties Extension (>= 0.0.34)

- Algorithm bisa push dynamic Properties
- Platform harus tolerant parsing

---

## 8.7 Task Behavior Changes

### 8.7.1 Auto Start

| Version | Behavior |
|------|---------|
| All | Task auto-start after create |

---

### 8.7.2 Restart Conditions

- Media update → task restart
- Parameter update → task restart
- Schedule inactive → task paused

---

## 8.8 Compatibility Rules (Platform Side)

Platform **WAJIB**:

1. Query capability, bukan hardcode
2. Ignore unknown fields
3. Support optional fields gracefully
4. Version-aware feature toggle

---

## 8.9 Recommended Platform Strategy

```text
Detect Version
     |
     v
Enable Feature If Supported
     |
     v
Fallback If Not Available
```

Contoh:
- Jika < 0.0.37 → ignore reporting ACK
- Jika < 0.0.43 → disable HTTP heartbeat

---

## 8.10 Breaking Behavior Checklist
|Change|Impact|
|-|-|
|Reporting ACK|Alarm retry logic|
|Custom reporting|Integration path|
|Extended heartbeat|Monitoring schema|
|New algorithm|UI dynamic render|

---
## 8.11 Deprecation Policy
- Field lama tidak langsung dihapus
- Field baru optional
- Breaking change diumumkan via version bump

## 8.12 Final Notes
- Platform tidak boleh assume version
- Semua behavior harus capability & version driven
- Dokumentasi ini adalah source of truth