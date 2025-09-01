# OU2GETHER Backend

OU2GETHER is the backend service of a student/alumni social network.  
It is built with **Django + Django REST Framework**, providing REST APIs to power the OU2GETHER mobile and web apps.

---

## 🚀 Features

- **Authentication & User Management**
  - User registration, login, password change, password reset.
  - Account verification & lock/unlock flow.
  - Role-based access: **Admin**, **Lecturer**, **Student**.
  - Admin panel with custom dashboards (user & post statistics).

- **Posts & Interactions**
  - Create text, media, and poll posts.
  - Like, love, haha, wow, sad, angry reactions.
  - Commenting with threaded replies & emoji reactions.
  - Share posts.

- **Polls**
  - Create polls with options and deadline.
  - Vote & view results (restricted counts for students).

- **Notifications**
  - Push notifications per user (posts, comments).
  - Device registration with token-based association.

- **Groups & Follow System**
  - Create & manage groups.
  - Follow/unfollow users.
  - Block/unblock users.

- **Chat (Conversations)**
  - One-to-one conversations.
  - Send messages with optional media.
  - Read/unread status tracking.

- **Admin Dashboard**
  - Custom stats: monthly, quarterly, yearly reports.
  - Post & comment moderation.
  - User management with default password rotation.

---

## 🛠️ Tech Stack

- **Python 3.12+**
- **Django 5.1.6**
- **Django REST Framework (DRF)**
- **Cloudinary** (media storage)
- **MySQL** (via PyMySQL)
- **OAuth2 (django-oauth-toolkit)**
- **drf-yasg** (Swagger / API docs)
- **CKEditor** (rich text editing in admin)

Dependencies are listed in [`requirements.txt`](./ou2getherapi/requirements.txt)

---

## 📦 Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/copcopne/OU2GETHER-backend.git
cd OU2GETHER-backend/ou2getherapi
```
### 2. Create & activate virtual environment
```bash
python -m venv venv
source venv\Scripts\activate
```
### 3. Install dependencies
```bash
pip install -r requirements.txt
```
### 4. Configure environment variables
Edit settings.py with:
```bash
SECRET_KEY=your_django_secret
DEBUG=True
ALLOWED_HOSTS=*
DATABASE_URL=mysql://username:password@localhost:3306/ou2gether
CLOUDINARY_URL=cloudinary://<api_key>:<api_secret>@<cloud_name>
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_password
```
### 5. Create MySQL database
```bash
CREATE DATABASE ou2gether CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
### 6. Run migrations
```bash
python manage.py migrate
```
### 7. Create superuser
```bash
python manage.py createsuperuser
```
### 8. Run development server
```bash
python manage.py runserver
```