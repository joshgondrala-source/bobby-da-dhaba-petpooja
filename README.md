🍽 QR-Based Restaurant Ordering, Kitchen & Billing Management System

A modern QR-based Restaurant Ordering & Kitchen Management System built using **Python, Flask, SQLite, HTML, CSS, and JavaScript**.

Customers can simply scan a QR code, browse the digital menu, place multiple orders, request the bill, while the kitchen, manager, and owner can manage restaurant operations through dedicated dashboards.

This project was developed to simplify restaurant operations by eliminating paper menus, reducing waiter dependency, and improving communication between customers, kitchen staff, and management.

---

# 🚀 Features

## 👨‍🍳 Customer Module

- Scan QR code to access the menu
- Enter table number
- Browse menu by categories
- View detailed item information
- Add items to a shared table cart
- Update quantities and special instructions
- Place multiple orders
- View previously placed orders
- Request bill
- Mobile-friendly interface
- Sticky bottom navigation

---

## 🍳 Kitchen Module

- Live Kitchen Order Ticket (KOT) Dashboard
- Automatic NEW TABLE / RUNNING TABLE identification
- Multiple KOT support for the same table
- Real-time order updates
- Chronological order management

---

## 👨‍💼 Manager Module

- View pending bill requests
- Generate consolidated bill
- Automatic GST calculation
- Discount support
- Mark payment received
- Automatic table availability management

---

## 👑 Owner Dashboard

- Total Revenue
- Daily Sales
- Total Bills Processed
- GST Collection
- Real-time business overview

---

# 💡 Key Highlights

- Persistent SQLite Database
- Shared Cart for Every Table
- Multiple Orders from Same Table
- Automatic NEW TABLE / RUNNING TABLE KOT Logic
- Single Consolidated Bill
- Automatic Table Status Management
- Mobile Responsive UI
- Real-Time Kitchen Updates
- Clean Dashboard Design

---

# 🛠 Tech Stack

### Backend
- Python
- Flask

### Frontend
- HTML
- CSS
- JavaScript
- Jinja2 Templates

### Database
- SQLite

### Version Control
- Git
- GitHub

### Deployment
- Render

---

# 📂 Project Structure

```
restaurant-ordering-system/

│
├── app.py
├── restaurant.db
├── requirements.txt
│
├── static/
│   ├── css/
│   ├── images/
│   └── js/
│
├── templates/
│   ├── home.html
│   ├── menu.html
│   ├── item.html
│   ├── cart.html
│   ├── orders.html
│   ├── kitchen.html
│   ├── manager.html
│   ├── owner.html
│   ├── final_bill.html
│   └── ...
│
└── README.md
```

---

# 🔄 System Workflow

```
Customer

↓

Scan QR Code

↓

Enter Table Number

↓

Browse Menu

↓

Add Items to Shared Cart

↓

Place Order

↓

Kitchen Receives KOT

↓

Customer Places More Orders (Optional)

↓

Kitchen Receives RUNNING TABLE KOT

↓

Customer Requests Bill

↓

Manager Generates Final Bill

↓

Payment Received

↓

Table Becomes Available

↓

Owner Dashboard Updated
```

---

# 💾 Database Design

The application uses **SQLite** for persistent data storage.

### Tables Used

- `tables`
- `table_cart_items`
- `kots`
- `kot_items`
- `bill_requests`

The database stores:

- Table information
- Shared cart data
- Kitchen Order Tickets (KOTs)
- Ordered items
- Bill requests
- Payment status

Unlike in-memory storage, all information remains available even if the application is restarted.

---

# 🍽 Multiple KOT Workflow

The system allows customers to place multiple orders without closing the table.

Example:

```
Table 5

↓

Order 1

↓

NEW TABLE

↓

Order 2

↓

RUNNING TABLE

↓

Order 3

↓

RUNNING TABLE

↓

Manager Generates One Final Bill

↓

Payment Completed
```

---

# 🌍 Real-World Validation

This project was **pilot-tested in a live restaurant environment** to validate the complete ordering workflow.

The testing covered:

- Customer ordering experience
- Shared table carts
- Multiple KOT generation
- Kitchen workflow
- Billing process

The feedback received during testing helped improve the user interface and overall workflow.

---

# 🔮 Future Improvements

- Online Payment Integration
- Waiter Dashboard
- Inventory Management
- Cloud Database (PostgreSQL)
- Push Notifications
- Customer Login System
- Analytics Dashboard
- AI-based Sales Insights
- Multi-Branch Restaurant Support

---

# 👨‍💻 Author

**G. Jyothi Swaroop**

Chemical Engineering Undergraduate  
National Institute of Technology Warangal

📧 Email:
- joshgondrala@gmail.com
- gj25chb0b19@student.nitw.ac.in

🔗 GitHub:
https://github.com/joshgondrala-source

🔗 LinkedIn:
https://www.linkedin.com/in/jyothi-swaroop-gondrala-2303373a6

---

# ⭐ Support

If you found this project helpful or interesting, consider giving it a ⭐ on GitHub.

Your support motivates me to build and share more real-world projects!
