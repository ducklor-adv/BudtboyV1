# 🔄 ขั้นตอนการ Migrate จาก Replit ไปยัง Local Development

## 📋 Overview

คู่มือนี้จะแนะนำวิธีการย้ายโปรเจกต์ BudtBoy จาก Replit มาทำงานบน localhost ด้วย VS Code

## ✅ สิ่งที่ได้ทำแล้ว

โครงสร้างใหม่ที่สร้างขึ้น:

```
✅ app/                     # โค้ดแอปพลิเคชันทั้งหมด
✅ config/                  # Configuration files
✅ .env.example             # ตัวอย่าง environment variables
✅ requirements.txt         # Python dependencies
✅ run.py                   # Entry point ใหม่
✅ migrate_data.py          # สคริปต์ย้ายข้อมูล
✅ README.md                # คู่มือหลัก
✅ SETUP_GUIDE.md           # คู่มือติดตั้ง
✅ .gitignore               # Git ignore rules
```

## 🎯 ขั้นตอนการ Migrate

### ขั้นตอนที่ 1: เตรียมไฟล์

```bash
# 1. Rename main.py เดิมเพื่อเก็บไว้เป็น backup
mv main.py main.py.old

# หรือบน Windows
ren main.py main.py.old
```

### ขั้นตอนที่ 2: ติดตั้ง Dependencies

```bash
# สร้าง virtual environment
python -m venv venv

# เปิดใช้งาน virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# ติดตั้ง packages
pip install -r requirements.txt
```

### ขั้นตอนที่ 3: ตั้งค่า Environment Variables

```bash
# คัดลอกไฟล์ตัวอย่าง
cp .env.example .env

# แก้ไขไฟล์ .env (ใช้ text editor ที่ชอบ)
# ⚠️ สำคัญ: เปลี่ยนค่าต่อไปนี้
# - SECRET_KEY (สร้างค่าสุ่มใหม่)
# - ADMIN_MASTER_PASSWORD (เปลี่ยนรหัสผ่าน admin)
```

### ขั้นตอนที่ 4: ตั้งค่า VS Code (Optional แต่แนะนำ)

```bash
# คัดลอกไฟล์ตั้งค่า VS Code
cp .vscode/settings.json.example .vscode/settings.json
cp .vscode/launch.json.example .vscode/launch.json

# แก้ไข path ให้ตรงกับระบบของคุณถ้าจำเป็น
```

### ขั้นตอนที่ 5: ย้ายข้อมูล (ถ้ามีฐานข้อมูลเก่า)

```bash
# รันสคริปต์ย้ายข้อมูล
python migrate_data.py
```

สคริปต์นี้จะ:
- ✅ สำรองฐานข้อมูลเก่า (`budtboy_preview.db`)
- ✅ คัดลอกข้อมูลไปยังฐานข้อมูลใหม่ (`budtboy_local.db`)
- ✅ แสดงสรุปการย้ายข้อมูล

### ขั้นตอนที่ 6: รันแอปพลิเคชัน

```bash
# รันแอป
python run.py
```

เปิดเบราว์เซอร์ไปที่: `http://localhost:5000`

## 🔍 การตรวจสอบ

### ตรวจสอบว่าแอปทำงานได้:

1. ✅ เปิด `http://localhost:5000` ได้
2. ✅ หน้า login แสดงผลปกติ
3. ✅ Login ด้วย admin999 ได้
4. ✅ ดูโปรไฟล์ได้
5. ✅ อัพโหลดรูปได้
6. ✅ เพิ่ม bud ได้
7. ✅ เขียนรีวิวได้

### ตรวจสอบฐานข้อมูล:

```bash
# ใช้ SQLite command line
sqlite3 budtboy_local.db "SELECT COUNT(*) FROM users;"
sqlite3 budtboy_local.db "SELECT COUNT(*) FROM buds_data;"
sqlite3 budtboy_local.db "SELECT COUNT(*) FROM reviews;"
```

## 📝 ความแตกต่างระหว่างเวอร์ชันเก่าและใหม่

### โครงสร้างโค้ด

**เก่า (Replit):**
- ทุกอย่างอยู่ใน `main.py` (7000+ บรรทัด)
- ใช้ PostgreSQL และ SQLite
- พึ่งพา Replit environment variables

**ใหม่ (Local):**
- แยกเป็นโมดูลย่อยๆ
- ใช้ SQLite สำหรับ development
- ใช้ไฟล์ `.env` สำหรับ configuration

### Configuration

**เก่า:**
```python
# ใน main.py
app.secret_key = 'budtboy-secret-key-2024'
DATABASE_URL = os.environ.get('DATABASE_URL')
```

**ใหม่:**
```python
# ใน config/config.py
SECRET_KEY = os.environ.get('SECRET_KEY')

# ใน .env
SECRET_KEY=your-random-secret-key
```

### Routes

**เก่า:**
```python
# ใน main.py
@app.route('/profile')
def profile():
    # ...
```

**ใหม่:**
```python
# ใน app/routes/main.py
@main_bp.route('/profile')
@login_required
def profile():
    # ...
```

## 🔧 Troubleshooting

### ปัญหา: Import Error

**อาการ:** `ModuleNotFoundError: No module named 'app'`

**แก้ไข:**
```bash
# ตรวจสอบว่าอยู่ใน virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# ติดตั้ง dependencies ใหม่
pip install -r requirements.txt
```

### ปัญหา: Database Error

**อาการ:** `no such table: users`

**แก้ไข:**
```bash
# ลบฐานข้อมูลและสร้างใหม่
rm budtboy_local.db
python run.py
```

### ปัญหา: Template Not Found

**อาการ:** `jinja2.exceptions.TemplateNotFound`

**แก้ไข:**
```bash
# ตรวจสอบว่า templates ถูกคัดลอกแล้ว
ls app/templates/

# ถ้ายังไม่มี ให้คัดลอก
# Windows:
xcopy /E /I templates app\templates
# macOS/Linux:
cp -r templates/* app/templates/
```

### ปัญหา: Static Files 404

**อาการ:** CSS/JS ไม่โหลด

**แก้ไข:**
```bash
# ตรวจสอบ path ใน HTML templates
# ต้องใช้ url_for('static', filename='...')
```

## 📚 ไฟล์สำคัญ

### ไฟล์ที่ต้องแก้ไข

- ✅ `.env` - Environment variables
- ⚠️ `app/routes/*.py` - ถ้าต้องการเพิ่ม routes
- ⚠️ `app/models/database.py` - ถ้าต้องการแก้ database schema
- ⚠️ `config/config.py` - ถ้าต้องการเพิ่ม configuration

### ไฟล์ที่ไม่ควรแก้

- ❌ `run.py` - เว้นแต่มีเหตุผลพิเศษ
- ❌ `app/__init__.py` - เว้นแต่ต้องการเพิ่ม extension
- ❌ `requirements.txt` - อัพเดทด้วย `pip freeze > requirements.txt`

## 🎓 การพัฒนาต่อ

### เพิ่ม Route ใหม่

```python
# ใน app/routes/main.py
@main_bp.route('/new-page')
@login_required
def new_page():
    return render_template('new_page.html')
```

### เพิ่ม API Endpoint

```python
# ใน app/routes/api.py
@api_bp.route('/new-api', methods=['POST'])
@api_login_required
def new_api():
    data = request.get_json()
    # Process data
    return jsonify({'success': True})
```

### เพิ่ม Database Table

```python
# ใน app/models/database.py
# แก้ไข method init_db()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS new_table (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
```

## 🚀 Deployment (ในอนาคต)

เมื่อต้องการ deploy:

1. **เปลี่ยน configuration:**
   ```bash
   FLASK_ENV=production
   DEBUG=False
   ```

2. **ใช้ production server:**
   ```bash
   # ติดตั้ง Gunicorn
   pip install gunicorn

   # รันด้วย Gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app('production')"
   ```

3. **ตั้งค่า PostgreSQL** (แนะนำสำหรับ production)

4. **ตั้งค่า Nginx/Apache** เป็น reverse proxy

5. **เปิดใช้ HTTPS**

## ✅ Checklist ก่อน Commit

- [ ] ลบ `main.py.old` ออก (หรือเพิ่มใน .gitignore)
- [ ] ไม่ commit ไฟล์ `.env`
- [ ] ไม่ commit ไฟล์ `.db`
- [ ] ไม่ commit folder `venv/`
- [ ] อัพเดท `.gitignore` ถ้าจำเป็น
- [ ] เขียน commit message ที่ชัดเจน

## 🎉 สำเร็จ!

ตอนนี้คุณมี BudtBoy ที่:
- ✅ ทำงานบน localhost
- ✅ โค้ดเป็นระเบียบและแยกโมดูล
- ✅ ปลอดภัยกว่าเดิม
- ✅ พัฒนาต่อได้ง่าย
- ✅ Debug ได้สะดวก

**Happy Coding! 🌿**
