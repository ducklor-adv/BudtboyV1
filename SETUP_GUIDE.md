# 📚 คู่มือการติดตั้งและใช้งาน BudtBoy

## 🎯 สำหรับผู้ใช้ Windows

### 1. ติดตั้ง Python

1. ดาวน์โหลด Python จาก [python.org](https://www.python.org/downloads/)
2. เลือก Python 3.11 หรือใหม่กว่า
3. **สำคัญ**: เลือก "Add Python to PATH" ระหว่างการติดตั้ง
4. คลิก "Install Now"

### 2. ตรวจสอบการติดตั้ง

เปิด Command Prompt หรือ PowerShell แล้วรันคำสั่ง:

```bash
python --version
```

ถ้าเห็นเวอร์ชัน Python แสดงว่าติดตั้งสำเร็จ

### 3. ติดตั้งโปรเจกต์

```bash
# 1. เปิด Command Prompt/PowerShell
# 2. ไปที่โฟลเดอร์โปรเจกต์
cd path\to\BudtBoy

# 3. สร้าง Virtual Environment
python -m venv venv

# 4. เปิดใช้งาน Virtual Environment
venv\Scripts\activate

# 5. ติดตั้ง dependencies
pip install -r requirements.txt

# 6. คัดลอกและแก้ไขไฟล์ .env
copy .env.example .env
notepad .env

# 7. (Optional) ย้ายข้อมูลจากฐานข้อมูลเก่า
python migrate_data.py

# 8. รันแอป
python run.py
```

### 4. เปิดใช้งาน

เปิดเบราว์เซอร์และไปที่: `http://localhost:5000`

---

## 🍎 สำหรับผู้ใช้ macOS/Linux

### 1. ติดตั้ง Python

Python มักจะติดตั้งมาแล้วใน macOS/Linux ตรวจสอบด้วย:

```bash
python3 --version
```

ถ้ายังไม่มี ติดตั้งด้วย:

**macOS (ใช้ Homebrew):**
```bash
brew install python@3.11
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
```

### 2. ติดตั้งโปรเจกต์

```bash
# 1. เปิด Terminal
# 2. ไปที่โฟลเดอร์โปรเจกต์
cd path/to/BudtBoy

# 3. สร้าง Virtual Environment
python3 -m venv venv

# 4. เปิดใช้งาน Virtual Environment
source venv/bin/activate

# 5. ติดตั้ง dependencies
pip install -r requirements.txt

# 6. คัดลอกและแก้ไขไฟล์ .env
cp .env.example .env
nano .env  # หรือใช้ text editor อื่น

# 7. (Optional) ย้ายข้อมูลจากฐานข้อมูลเก่า
python migrate_data.py

# 8. รันแอป
python run.py
```

---

## ⚙️ การตั้งค่า .env

แก้ไขไฟล์ `.env` ดังนี้:

```bash
# 1. สร้าง Secret Key แบบสุ่ม
SECRET_KEY=<กด random ปุ่มบนคีย์บอร์ด 30-40 ครั้ง>

# 2. ตั้งรหัสผ่าน Admin ใหม่
ADMIN_MASTER_PASSWORD=<รหัสผ่านที่แข็งแกร่ง>

# 3. (Optional) ตั้งค่าอีเมล ถ้าต้องการส่งอีเมล
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
```

### วิธีสร้าง App Password สำหรับ Gmail:

1. ไปที่ Google Account Settings
2. Security → 2-Step Verification (เปิดใช้งาน)
3. App passwords → Select app: Mail → Generate
4. คัดลอก password 16 หลักมาใส่ใน `MAIL_PASSWORD`

---

## 🗄️ การย้ายข้อมูลจากฐานข้อมูลเก่า

ถ้าคุณมีข้อมูลเก่าใน `budtboy_preview.db`:

```bash
# รันสคริปต์ย้ายข้อมูล
python migrate_data.py
```

สคริปต์จะ:
1. สำรองฐานข้อมูลเก่า
2. คัดลอกข้อมูลไปยังฐานข้อมูลใหม่
3. แสดงสรุปการย้ายข้อมูล

---

## 🚀 การรันแอป

### Development Mode (สำหรับพัฒนา)

```bash
python run.py
```

แอปจะรันที่: `http://localhost:5000`

### การเปลี่ยน Port

แก้ไขไฟล์ `.env`:

```bash
PORT=8080
```

หรือรันด้วยคำสั่ง:

```bash
PORT=8080 python run.py
```

---

## 🔐 Admin Login

**Username:** `admin999`
**Password:** ตามที่ตั้งใน `ADMIN_MASTER_PASSWORD` ในไฟล์ `.env`

URL Admin: `http://localhost:5000/admin/login`

---

## 🐛 แก้ปัญหา

### ปัญหา: ModuleNotFoundError

```bash
# ตรวจสอบว่าเปิด virtual environment แล้ว
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# ติดตั้ง dependencies ใหม่
pip install -r requirements.txt
```

### ปัญหา: Port already in use

```bash
# เปลี่ยน port ในไฟล์ .env
PORT=8080
```

### ปัญหา: Database is locked

```bash
# ปิดแอปที่กำลังรัน (Ctrl+C)
# ลบไฟล์ lock
rm budtboy_local.db-journal

# รันใหม่
python run.py
```

### ปัญหา: Templates not found

```bash
# ตรวจสอบว่า templates ถูกคัดลอกแล้ว
ls app/templates/

# ถ้ายังไม่มี ให้คัดลอกด้วยตัวเอง
cp -r templates/* app/templates/
```

---

## 📁 โครงสร้างไฟล์

```
BudtBoy/
├── app/                    # แอปพลิเคชันหลัก
│   ├── __init__.py         # Application factory
│   ├── models/             # Database models
│   ├── routes/             # Routes (auth, main, admin, api)
│   ├── utils/              # Utilities
│   ├── static/             # CSS, JS, images
│   └── templates/          # HTML templates
├── config/                 # Configuration
├── uploads/                # User uploads
├── logs/                   # Application logs
├── .env                    # Environment variables (ไม่ commit)
├── .env.example            # ตัวอย่าง
├── requirements.txt        # Dependencies
├── run.py                  # Entry point
├── migrate_data.py         # Data migration
└── README.md              # คู่มือ
```

---

## 🔄 การอัพเดทโค้ด

```bash
# 1. Pull โค้ดใหม่
git pull

# 2. เปิด virtual environment
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# 3. อัพเดท dependencies
pip install -r requirements.txt --upgrade

# 4. รันแอป
python run.py
```

---

## 📝 Tips

### 1. ใช้ VS Code

ติดตั้ง extensions:
- Python (Microsoft)
- Pylance
- Python Debugger

### 2. การ Debug

ใน VS Code สร้างไฟล์ `.vscode/launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Flask",
            "type": "python",
            "request": "launch",
            "module": "flask",
            "env": {
                "FLASK_APP": "run.py",
                "FLASK_ENV": "development"
            },
            "args": [
                "run",
                "--no-debugger",
                "--no-reload"
            ],
            "jinja": true
        }
    ]
}
```

### 3. ดู Database

ใช้ SQLite Viewer extension ใน VS Code หรือโปรแกรม:
- [DB Browser for SQLite](https://sqlitebrowser.org/)
- [DBeaver](https://dbeaver.io/)

---

## 🆘 ขอความช่วยเหลือ

ถ้ามีปัญหา:

1. ตรวจสอบ logs ที่ `logs/budtboy.log`
2. ดู console output
3. อ่าน error message ให้ละเอียด
4. ค้นหาใน Google/Stack Overflow

---

**สนุกกับการพัฒนา! 🌿**
