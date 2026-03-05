# 🚀 RMF AI Dreams - Deployment Guide

## Local Development

### Method 1: Direct Run
```bash
streamlit run rmf_ai_app.py
```

### Method 2: Using Launch Script
```bash
./run_rmf.sh
```

---

## Cloud Deployment Options

### 1. Streamlit Cloud (Recommended for MVP)

**Steps:**
1. Push code to GitHub repository
2. Go to https://share.streamlit.io
3. Connect your GitHub account
4. Select repository and branch
5. Set main file: `rmf_ai_app.py`
6. Deploy

**Pros:**
- Free tier available
- Easy deployment
- Auto-updates from GitHub
- Built-in SSL

---

### 2. Heroku

**Steps:**
```bash
# Create Procfile
echo "web: streamlit run rmf_ai_app.py --server.port $PORT" > Procfile

# Create runtime.txt
echo "python-3.11.0" > runtime.txt

# Deploy
heroku create rmf-ai-dreams
git push heroku main
```

**Pros:**
- Free tier available
- Easy scaling
- Add-ons ecosystem

---

### 3. AWS EC2

**Steps:**
1. Launch EC2 instance (Ubuntu 22.04)
2. SSH into instance
3. Install dependencies:
```bash
sudo apt update
sudo apt install python3-pip -y
pip3 install -r requirements_rmf.txt
```
4. Run app:
```bash
streamlit run rmf_ai_app.py --server.port 8501 --server.address 0.0.0.0
```
5. Configure security group (port 8501)

**Pros:**
- Full control
- Scalable
- Custom domain support

---

### 4. Docker Deployment

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements_rmf.txt .
RUN pip install -r requirements_rmf.txt

COPY rmf_ai_app.py .

EXPOSE 8501

CMD ["streamlit", "run", "rmf_ai_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

**Build & Run:**
```bash
docker build -t rmf-ai-dreams .
docker run -p 8501:8501 rmf-ai-dreams
```

---

### 5. DigitalOcean App Platform

**Steps:**
1. Create new app
2. Connect GitHub repository
3. Set build command: `pip install -r requirements_rmf.txt`
4. Set run command: `streamlit run rmf_ai_app.py --server.port 8080`
5. Deploy

---

## Environment Variables (for production)

Create `.env` file:
```
OPENAI_API_KEY=your_key_here
DATABASE_URL=sqlite:///rmf_ai_memory.db
SECRET_KEY=your_secret_key
OWNER_EMAIL=reem@example.com
```

---

## Security Checklist

- [ ] Enable HTTPS/SSL
- [ ] Set strong authentication
- [ ] Restrict Owner access
- [ ] Enable database backups
- [ ] Set up monitoring
- [ ] Configure firewall rules
- [ ] Use environment variables for secrets
- [ ] Enable rate limiting

---

## Performance Optimization

1. **Database:**
   - Use PostgreSQL for production
   - Enable connection pooling
   - Add indexes on frequently queried columns

2. **Caching:**
   - Use `@st.cache_data` for expensive operations
   - Implement Redis for session storage

3. **Scaling:**
   - Use load balancer for multiple instances
   - Enable auto-scaling based on traffic

---

## Monitoring & Logging

**Recommended Tools:**
- **Sentry** - Error tracking
- **LogRocket** - Session replay
- **Datadog** - Performance monitoring
- **Uptime Robot** - Uptime monitoring

---

## Backup Strategy

**Database Backup:**
```bash
# Daily backup
sqlite3 rmf_ai_memory.db ".backup 'backup_$(date +%Y%m%d).db'"

# Automated backup script
0 2 * * * /path/to/backup_script.sh
```

---

## Custom Domain Setup

1. Purchase domain (e.g., rmfai.com)
2. Configure DNS:
   - A record: @ → Server IP
   - CNAME: www → @
3. Enable SSL (Let's Encrypt)
4. Update Streamlit config

---

## Troubleshooting

**Port already in use:**
```bash
streamlit run rmf_ai_app.py --server.port 8502
```

**Database locked:**
```bash
# Check for zombie processes
ps aux | grep streamlit
kill -9 <PID>
```

**Memory issues:**
```bash
# Increase memory limit
streamlit run rmf_ai_app.py --server.maxUploadSize 200
```

---

## Next Steps After Deployment

1. Test all features in production
2. Set up analytics (Google Analytics)
3. Configure email notifications
4. Enable user feedback system
5. Set up CI/CD pipeline
6. Create user documentation
7. Plan feature roadmap

---

**🖤 RMF AI DREAMS - Ready for Production 💀🔥**
