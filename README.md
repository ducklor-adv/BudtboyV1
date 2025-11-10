# 🌿 BudtBoy - Cannabis Strain Management Platform

BudtBoy เป็นแพลตฟอร์มสำหรับจัดการข้อมูลสายพันธุ์กัญชา รีวิว และชุมชน สำหรับผู้เพาะปลูก Budtender และผู้บริโภค

## ✨ คุณสมบัติหลัก

### สำหรับผู้ใช้ทั่วไป
- 🔐 ระบบลงทะเบียนและเข้าสู่ระบบ (Email/Password)
- 👤 จัดการโปรไฟล์และรูปภาพ
- 🌱 เพิ่ม/แก้ไข/ลบข้อมูลสายพันธุ์กัญชา
- ⭐ เขียนรีวิวและให้คะแนน
- 👥 ระบบเพื่อนและติดตามกิจกรรม
- 🏆 เข้าร่วมกิจกรรม/ประกวด
- 🔍 ค้นหาสายพันธุ์และผู้เพาะปลูก

### สำหรับ Admin
- 📊 Dashboard สถิติ
- 👥 อนุมัติ/จัดการผู้ใช้
- 🌱 ตรวจสอบ/ลบเนื้อหา
- 🏆 จัดการกิจกรรม/ประกวด
- ⚙️ ตั้งค่าระบบ

## 🚀 การติดตั้งและใช้งาน

### ข้อกำหนดระบบ
- Python 3.11 หรือสูงกว่า
- pip (Python package manager)

### ขั้นตอนการติดตั้ง

1. **Clone โปรเจกต์**
```bash
git clone <repository-url>
cd BudtBoy
```

2. **สร้าง Virtual Environment (แนะนำ)**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

3. **ติดตั้ง Dependencies**
```bash
pip install -r requirements.txt
```

4. **ตั้งค่า Environment Variables**
```bash
# คัดลอกไฟล์ตัวอย่าง
cp .env.example .env

# แก้ไขไฟล์ .env ด้วย text editor
# ⚠️ สำคัญ: เปลี่ยน SECRET_KEY และ ADMIN_MASTER_PASSWORD
```

5. **รันแอปพลิเคชัน**
```bash
python run.py
```

6. **เปิดเบราว์เซอร์**
```
http://localhost:5000
```

## 📁 โครงสร้างโปรเจกต์

```
BudtBoy/
├── app/
│   ├── __init__.py          # Application factory
│   ├── models/              # Database models
│   │   ├── __init__.py
│   │   └── database.py      # Database manager
│   ├── routes/              # Route blueprints
│   │   ├── __init__.py
│   │   ├── auth.py          # Authentication routes
│   │   ├── main.py          # Main page routes
│   │   ├── admin.py         # Admin routes
│   │   └── api.py           # API endpoints
│   ├── utils/               # Utility modules
│   │   ├── __init__.py
│   │   ├── auth.py          # Auth helpers
│   │   ├── cache.py         # Cache manager
│   │   ├── validators.py    # Input validators
│   │   └── helpers.py       # Helper functions
│   ├── static/              # Static files (CSS, JS, images)
│   └── templates/           # HTML templates
├── config/
│   ├── __init__.py
│   └── config.py            # Configuration settings
├── uploads/                 # User uploaded files
├── attached_assets/         # Application assets
├── logs/                    # Application logs
├── .env                     # Environment variables (ไม่ commit)
├── .env.example             # ตัวอย่าง environment variables
├── .gitignore              # Git ignore rules
├── requirements.txt         # Python dependencies
├── run.py                   # Application entry point
└── README.md               # คู่มือนี้
```

## ⚙️ การตั้งค่า

### Environment Variables

แก้ไขไฟล์ `.env` เพื่อตั้งค่าต่างๆ:

```bash
# Flask Configuration
SECRET_KEY=your-secret-key-here-change-this-to-random-string
FLASK_ENV=development
DEBUG=True

# Database
DATABASE_PATH=budtboy_local.db

# Email (Optional - สำหรับส่งอีเมล)
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password

# Admin
ADMIN_MASTER_PASSWORD=YourStrongPasswordHere123!
```

### Admin Login

**Default Admin Account:**
- Username: `admin999`
- Password: ตามที่ตั้งใน `ADMIN_MASTER_PASSWORD` environment variable

⚠️ **สำคัญ**: เปลี่ยนรหัสผ่าน Admin ทันทีเมื่อใช้งานจริง

## 🔒 ความปลอดภัย

โปรเจกต์ใหม่นี้ได้ปรับปรุงความปลอดภัยหลายจุด:

- ✅ แยกโครงสร้างโค้ดเป็นโมดูล (Modular architecture)
- ✅ ใช้ Blueprint สำหรับ routes
- ✅ Password hashing ด้วย bcrypt (12 rounds)
- ✅ Session management ที่ปลอดภัย
- ✅ Input validation
- ✅ File upload security
- ✅ Environment-based configuration

### สิ่งที่ควรทำก่อนใช้งานจริง (Production):

1. เปลี่ยน `SECRET_KEY` เป็นค่าสุ่มที่ปลอดภัย
2. เปลี่ยน `ADMIN_MASTER_PASSWORD`
3. ตั้ง `FLASK_ENV=production` และ `DEBUG=False`
4. ใช้ PostgreSQL แทน SQLite
5. ตั้งค่า HTTPS และ SSL certificates
6. เพิ่ม Rate Limiting (Flask-Limiter)
7. เพิ่ม CSRF Protection (Flask-WTF)
8. ตั้งค่า Firewall และ Security headers

## 🗄️ Database

โปรเจกต์ใช้ SQLite สำหรับ local development เพราะติดตั้งและใช้งานง่าย

### Tables หลัก:
- `users` - ข้อมูลผู้ใช้
- `admin_accounts` - บัญชี admin
- `buds_data` - ข้อมูลสายพันธุ์กัญชา
- `reviews` - รีวิว
- `activities` - กิจกรรม/ประกวด
- `friends` - ความสัมพันธ์ระหว่างผู้ใช้
- `referrals` - ระบบแนะนำเพื่อน

Database จะถูกสร้างอัตโนมัติเมื่อรันแอปครั้งแรก

## 📝 API Endpoints

### Authentication
- `POST /login` - เข้าสู่ระบบ
- `POST /signup` - ลงทะเบียน
- `GET /logout` - ออกจากระบบ

### Profile
- `GET /api/profile` - ดูโปรไฟล์
- `PUT /api/profile` - แก้ไขโปรไฟล์
- `POST /api/profile/image` - อัพโหลดรูปโปรไฟล์

### Buds
- `GET /api/buds` - ดูรายการ buds
- `GET /api/buds/<id>` - ดูรายละเอียด bud
- `POST /api/buds` - สร้าง bud ใหม่
- `DELETE /api/buds/<id>` - ลบ bud

### Reviews
- `GET /api/reviews` - ดูรายการรีวิว
- `POST /api/reviews` - สร้างรีวิวใหม่

## 🛠️ Development

### รัน Development Server
```bash
python run.py
```

### ดู Logs
```bash
# Logs จะถูกบันทึกที่
logs/budtboy.log
```

### Database Management
```bash
# ดู database schema
python -c "from app.models import Database; db = Database('budtboy_local.db'); db.init_db()"
```

## 🐛 Troubleshooting

### ปัญหา: Python ไม่พบ
```bash
# ตรวจสอบว่าติดตั้ง Python แล้ว
python --version

# หรือลองใช้
python3 --version
```

### ปัญหา: Import Error
```bash
# ติดตั้ง dependencies ใหม่
pip install -r requirements.txt
```

### ปัญหา: Database Error
```bash
# ลบ database และสร้างใหม่
rm budtboy_local.db
python run.py
```

## 📄 License

Copyright © 2024 BudtBoy

## 🤝 Contributing

ยินดีรับ Pull Requests และ Issues

## 📧 Contact

หากมีคำถามหรือปัญหา กรุณาติดต่อผ้านพัฒนา

---

**สนุกกับการใช้งาน BudtBoy! 🌿**
