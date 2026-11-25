from datetime import date, timedelta

DOCTORS = [
    {"id": "d1", "name": "Dr. Ananya Rao", "specialty": "Cardiologist", "times": ["09:30", "10:30", "11:30", "15:00"]},
    {"id": "d2", "name": "Dr. Vikram Mehta", "specialty": "Dermatologist", "times": ["10:00", "12:00", "16:00", "17:00"]},
    {"id": "d3", "name": "Dr. Sara Thomas", "specialty": "Pediatrician", "times": ["09:00", "11:00", "14:00", "16:30"]},
    {"id": "d4", "name": "Dr. Arjun Iyer", "specialty": "Orthopedic Surgeon", "times": ["10:00", "13:00", "15:30"]},
    {"id": "d5", "name": "Dr. Neha Kapoor", "specialty": "General Physician", "times": ["09:00", "10:00", "11:00", "12:00", "17:30"]},
]

DAYS_AHEAD = 4

appointments = []
next_id = 1


def upcoming_dates():
    today = date.today()
    return [(today + timedelta(days=i)).isoformat() for i in range(1, DAYS_AHEAD + 1)]


def clean_phone(phone):
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def find_doctor(query):
    query = query.lower().replace("dr.", "").replace("doctor", "").strip()
    for doctor in DOCTORS:
        if query in doctor["name"].lower() or query in doctor["specialty"].lower():
            return doctor
    for doctor in DOCTORS:
        if any(len(word) > 2 and word in doctor["name"].lower() for word in query.split()):
            return doctor
    return None


def is_taken(doctor_id, day, time):
    return any(
        a["doctor_id"] == doctor_id and a["date"] == day and a["time"] == time and a["status"] == "booked"
        for a in appointments
    )


def free_slots(doctor, day):
    return [t for t in doctor["times"] if not is_taken(doctor["id"], day, t)]


def doctors_with_slots():
    result = []
    for doctor in DOCTORS:
        slots = {day: free_slots(doctor, day) for day in upcoming_dates()}
        result.append({
            "id": doctor["id"],
            "name": doctor["name"],
            "specialty": doctor["specialty"],
            "times": doctor["times"],
            "slots": slots,
        })
    return result


def check_availability(doctor_name, day=None):
    doctor = find_doctor(doctor_name)
    if not doctor:
        return {"error": f"No doctor found for '{doctor_name}'."}

    days = [day] if day else upcoming_dates()
    if day and day not in upcoming_dates():
        return {"error": f"Bookings are open only for {', '.join(upcoming_dates())}."}

    slots = {d: free_slots(doctor, d) for d in days}
    return {"doctor": doctor["name"], "specialty": doctor["specialty"], "available": slots}


def book(doctor_name, day, time, phone, patient_name):
    global next_id

    doctor = find_doctor(doctor_name)
    if not doctor:
        return {"error": f"No doctor found for '{doctor_name}'."}

    phone = clean_phone(phone)
    if len(phone) != 10:
        return {"error": "Phone number must have 10 digits."}

    if day not in upcoming_dates() or time not in doctor["times"]:
        return {"error": "That slot does not exist. Check availability first."}

    if is_taken(doctor["id"], day, time):
        return {"error": "That slot was just taken. Offer another one."}

    appointment = {
        "id": f"A{next_id:03d}",
        "doctor_id": doctor["id"],
        "doctor": doctor["name"],
        "specialty": doctor["specialty"],
        "date": day,
        "time": time,
        "phone": phone,
        "patient": patient_name,
        "status": "booked",
    }
    next_id += 1
    appointments.append(appointment)
    return {"booked": appointment}


def active_for_phone(phone):
    return [a for a in appointments if a["phone"] == phone and a["status"] == "booked"]


def cancel(phone, appointment_id=None):
    phone = clean_phone(phone)
    matches = active_for_phone(phone)

    if appointment_id:
        matches = [a for a in matches if a["id"].lower() == appointment_id.lower()]

    if not matches:
        return {"error": "No active appointment found for this phone number."}

    if len(matches) > 1:
        return {"multiple": matches, "message": "Ask the caller which appointment to cancel, then call again with its id."}

    matches[0]["status"] = "cancelled"
    return {"cancelled": matches[0]}


def seed():
    days = upcoming_dates()
    book("Ananya Rao", days[0], "10:30", "9876543210", "Rahul Sharma")
    book("Sara Thomas", days[1], "14:00", "9123456780", "Priya Nair")


seed()
