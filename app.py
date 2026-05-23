from flask import Flask, render_template, request, jsonify, session, redirect
import face_recognition
import numpy as np
import base64
import os
import json
import math

app = Flask(__name__)
app.secret_key = 'super_secret_key_1234'

# --- 1. ข้อมูลจำลอง (Database Simulation) ---
all_seats = ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3", "D1", "D2", "D3"]
bookings = {} # เก็บข้อมูลการจอง

# ข้อมูลเส้นทางและราคา
korat_routes = [
    {"route": "นครราชสีมา - กรุงเทพฯ", "times": ["06:00", "09:00", "13:00"], "price": 191},
    {"route": "กรุงเทพฯ - นครราชสีมา", "times": ["07:00", "10:00", "14:00"], "price": 191},
    {"route": "นครราชสีมา - ขอนแก่น", "times": ["08:00", "11:00", "15:00"], "price": 155},
    {"route": "ขอนแก่น - นครราชสีมา", "times": ["09:00", "12:00", "16:00"], "price": 155},
    {"route": "นครราชสีมา - ชลบุรี", "times": ["07:30", "10:30", "20:00"], "price": 350},
    {"route": "ชลบุรี - นครราชสีมา", "times": ["08:30", "19:00"], "price": 350}
]

# --- 2. Route หน้าเว็บ (Frontend) ---

@app.route('/')
def index():
    """หน้าแรก: ค้นหาเที่ยวรถ"""
    locations = set()
    for r in korat_routes:
        parts = r["route"].split(" - ")
        for p in parts:
            locations.add(p)
    return render_template('index.html', locations=list(locations))

@app.route('/passenger_home')
def passenger_home():
    """หน้ารายการเที่ยวรถ / หน้าจอง"""
    # รับค่าจากหน้าค้นหา
    origin = request.args.get('origin')
    destination = request.args.get('destination')
    date = request.args.get('date')

    # สร้างชื่อเส้นทาง
    route_name = "ไม่ระบุเส้นทาง"
    if origin and destination:
        route_name = f"{origin} - {destination}"
    
    # ค้นหาราคา
    price = 0
    for r in korat_routes:
        if r['route'] == route_name:
            price = r.get('price', 0)
            break
            
    # กำหนดเวลา Default
    time_selected = "09:00"

    # ส่งข้อมูลไปหน้าเว็บ (แก้ไข seats=all_seats แล้ว)
    # เช็คชื่อไฟล์ดีๆ ว่าคุณใช้ passenger.html หรือ booking.html เป็นหน้าจอง
    return render_template('passenger.html',  # <-- ถ้าไฟล์หน้าจองชื่อ booking.html ให้ใช้ชื่อนี้
                           route=route_name, 
                           date=date, 
                           time=time_selected,
                           seats=all_seats, # <-- แก้ไขตรงนี้แล้ว (เติม s)
                           price=price)

@app.route('/select_seat')
def select_seat():
    """สำรอง: กรณีใช้หน้าแยก"""
    route_name = request.args.get('route', 'ไม่ระบุเส้นทาง')
    time = request.args.get('time', '-')
    date = request.args.get('date', '-')

    price = 0
    for r in korat_routes:
        if r['route'] == route_name:
            price = r.get('price', 0)
            break
            
    if price == 0:
         origin = request.args.get('origin')
         dest = request.args.get('destination')
         if origin and dest:
             check_name = f"{origin} - {dest}"
             for r in korat_routes:
                 if r['route'] == check_name:
                     price = r.get('price', 0)
                     route_name = check_name 
                     break

    return render_template('booking.html', 
                           route=route_name, 
                           time=time, 
                           date=date,
                           price=price)

@app.route('/summary')
def summary():
    seat = session.get('last_seat')
    info = bookings.get(seat)
    if not info: return redirect('/')

    # --- 👇 เพิ่มส่วนนี้: ค้นหาราคามาโชว์ในตั๋ว ---
    price = 0
    for r in korat_routes:
        if r['route'] == info['route']:
            price = r.get('price', 0)
            break
    # ----------------------------------------

    # สร้างเลขตั๋วแบบสุ่ม (เพื่อให้ดูเหมือนจริง)
    import random
    ticket_id = f"TKT-{random.randint(10000, 99999)}"

    # ส่งข้อมูลไปที่ summary.html
    return render_template('summary.html', info=info, price=price, ticket_id=ticket_id)
@app.route('/staff')
def staff():
    # ตรวจสอบว่าล็อกอินหรือยัง?
    if not session.get('is_admin'):
        return redirect('/staff_login')  # ถ้ายัง -> ดีดไปหน้าใส่รหัส
    
    return render_template('staff.html') # ถ้าล็อกอินแล้ว -> อนุญาตให้เข้า

@app.route('/bus-setup')
def bus_setup():
    return render_template('bus-map.html')

# --- 3. API Endpoints (Backend Logic) ---

@app.route('/api/seats')
def api_seats():
    if os.path.exists('seat_layout.json'):
        with open('seat_layout.json', 'r', encoding='utf-8') as f:
            layout = json.load(f)
        seats = [s['id'] for s in layout]
        return jsonify(seats)
    return jsonify(all_seats)
@app.route('/api/update_seat_status', methods=['POST'])
def update_seat_status():
    data = request.json
    seat = data.get('seat')
    status = data.get('status')

    if seat in bookings:
        bookings[seat]['checked_in'] = (status == 'onboard')

    return jsonify({"ok": True})


@app.route('/api/staff_stats')
def staff_stats():
    booked = len(bookings)
    checked_in = len([b for b in bookings.values() if b['checked_in']])
    remaining = booked - checked_in

    return jsonify({
        "booked": booked,
        "checked_in": checked_in,
        "remaining": remaining
    })
@app.route('/api/stats')
def get_stats():
    seat_status = {}
    current_seats = all_seats
    
    if os.path.exists('seat_layout.json'):
        with open('seat_layout.json', 'r', encoding='utf-8') as f:
            layout = json.load(f)
            current_seats = [s['id'] for s in layout]

    for s in current_seats:
        if s in bookings:
            if bookings[s]['checked_in']:
                seat_status[s] = "onboard"
            else:
                seat_status[s] = "booked"
        else:
            seat_status[s] = "empty"

    return jsonify({
        "booked": len(bookings),
        "onboard": len([p for p in bookings.values() if p['checked_in']]),
        "seats": seat_status
    })

@app.route('/api/book', methods=['POST'])
def api_book():
    data = request.json
    seat = data['seat']
    try:
        img_data = base64.b64decode(data['faces']['front'].split(",")[1])
        with open("last_reg.jpg", "wb") as f: f.write(img_data)
        
        image = face_recognition.load_image_file("last_reg.jpg")
        encodings = face_recognition.face_encodings(image)
        
        if len(encodings) > 0:
            encoding = encodings[0].tolist()
            bookings[seat] = {
                "name": data['name'],
                "phone": data['phone'],
                "route": data['route'],
                "date": data['date'],
                "seat": seat,
                "encoding": encoding,
                "checked_in": False
            }
            session['last_seat'] = seat
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "ไม่พบใบหน้า กรุณาถ่ายใหม่"})
    except Exception as e:
        print(e)
        return jsonify({"status": "error", "message": "เกิดข้อผิดพลาดในการประมวลผล"})

@app.route('/api/verify', methods=['POST'])
def api_verify():
    data = request.json
    try:
        img_bytes = base64.b64decode(data['image'].split(",")[1])
        with open("verify.jpg", "wb") as f: f.write(img_bytes)

        img = face_recognition.load_image_file("verify.jpg")
        frame_height, frame_width = img.shape[:2]
        locs = face_recognition.face_locations(img) 
        encs = face_recognition.face_encodings(img, locs)

        layout_data = []
        if os.path.exists('seat_layout.json'):
            with open('seat_layout.json', 'r', encoding='utf-8') as f:
                layout_data = json.load(f)

        results = []
        for loc, enc in zip(locs, encs):
            top, right, bottom, left = loc
            face_center_x = (left + right) / 2
            face_center_y = (top + bottom) / 2

            match_seat = "None"
            display_text = "Unknown"
            status_color = False 

            for seat, info in bookings.items():
                if face_recognition.compare_faces([np.array(info['encoding'])], enc, 0.5)[0]:
                    match_seat = seat
                    bookings[seat]['checked_in'] = True
                    
                    seat_info = next((item for item in layout_data if item["id"] == match_seat), None)
                    if seat_info:
                        target_x = (float(seat_info['left']) / 100) * frame_width
                        target_y = (float(seat_info['top']) / 100) * frame_height
                        dist = math.sqrt((face_center_x - target_x)**2 + (face_center_y - target_y)**2)
                        
                        if dist < 150: 
                            display_text = f"✔ {info['name']} ({seat})"
                            status_color = True
                        else:
                            display_text = f"❌ WRONG SEAT ({seat})"
                            status_color = False
                    else:
                        display_text = f"✔ {info['name']}"
                        status_color = True
                    break
            
            results.append({
                "box": loc, "name": display_text, 
                "seat": match_seat, "match": status_color 
            })
        return jsonify({"results": results})
    except:
        return jsonify({"results": []})

@app.route('/api/save-seats', methods=['POST'])
def save_seats():
    try:
        data = request.json
        with open('seat_layout.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return jsonify({"message": "บันทึกสำเร็จ!"})
    except:
        return jsonify({"message": "Error"}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    if data['username'] == 'admin' and data['password'] == '1234':
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Login Failed"})
# --- วางต่อท้ายใน app.py (ก่อนบรรทัด if __name__...) ---

@app.route('/check_booking', methods=['GET', 'POST'])
def check_booking():
    """หน้าตรวจสอบการจอง (ค้นหาด้วยเบอร์โทร)"""
    if request.method == 'POST':
        phone = request.form.get('phone')
        
        # ค้นหาคนจองจากเบอร์โทร
        found_info = None
        for seat, info in bookings.items():
            if info.get('phone') == phone:
                found_info = info
                break
        
        if found_info:
            # ถ้าเจอ -> หาราคาเพิ่ม
            price = 0
            for r in korat_routes:
                if r['route'] == found_info['route']:
                    price = r.get('price', 0)
                    break
            
            # สุ่มเลขตั๋วหลอกๆ
            import random
            ticket_id = f"TKT-{random.randint(10000, 99999)}"
            
            # ส่งไปหน้าตั๋ว (ใช้ไฟล์ summary.html ที่มีอยู่แล้ว)
            return render_template('summary.html', info=found_info, price=price, ticket_id=ticket_id)
        else:
            return render_template('check_booking.html', error="ไม่พบข้อมูลการจองของเบอร์นี้")

    return render_template('check_booking.html')

@app.route('/login')
def login_page():
    """หน้าเข้าสู่ระบบ"""
    return render_template('login.html')
@app.route('/history')
def history():
    # ดึงข้อมูลการจองทั้งหมดมาแสดง
    # (ถ้าโค้ดเดิมใช้ bookings.values() ก็ใช้อันนั้นได้เลย)
    if 'bookings' in globals():
        my_bookings = bookings.values()
    else:
        my_bookings = [] # กัน Error ถ้ายังไม่มีตัวแปร bookings
        
    return render_template('history.html', bookings=my_bookings)
@app.route('/staff_login', methods=['GET', 'POST'])
def staff_login_page():
    if request.method == 'POST':
        pwd = request.form.get('password')
        if pwd == '1234': 
            session['is_admin'] = True
            return redirect('/staff')
        else:
            return render_template('staff_login.html', error="รหัสผ่านไม่ถูกต้อง!")
    return render_template('staff_login.html')
@app.route('/api/staff_seats')
def staff_seats():
    if not os.path.exists('seat_layout.json'):
        return jsonify({"seats": [], "status": {}})

    with open('seat_layout.json', 'r', encoding='utf-8') as f:
        layout = json.load(f)

    # ✅ ใช้ที่นั่งจากผู้ดูแลจริง
    seats = [s['id'] for s in layout]

    status = {}
    for s in seats:
        if s in bookings:
            if bookings[s]['checked_in']:
                status[s] = 'onboard'
            else:
                status[s] = 'missing'
        else:
            status[s] = 'empty'

    return jsonify({
        "seats": seats,
        "status": status
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
if __name__ == '__main__':
    if not os.path.exists('static/images'):
        os.makedirs('static/images', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)
# --- เพิ่มใน app.py (ต่อท้าย ก่อนบรรทัด if __name__...) ---

