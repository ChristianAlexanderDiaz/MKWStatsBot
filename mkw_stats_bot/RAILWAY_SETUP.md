# 🚂 Railway Deployment Guide

## Free PostgreSQL + Bot Hosting on Railway

### **Step 1: Create Railway Account**
1. Go to [railway.app](https://railway.app)
2. Sign up with GitHub
3. Verify your account

### **Step 2: Deploy PostgreSQL Database**
1. Click "**New Project**"
2. Select "**Provision PostgreSQL**"
3. Railway automatically creates:
   - PostgreSQL instance
   - DATABASE_URL environment variable
   - **Free 500MB storage** (plenty for clan stats)

### **Step 3: Deploy Discord Bot**
1. In same project, click "**+ New**"
2. Select "**GitHub Repo**"
3. Connect your mkw_stats_bot repository
4. Railway auto-detects Python and installs requirements

### **Step 4: Configure Environment Variables**
In Railway dashboard, add these variables:

```bash
# Discord Bot Token (required)
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# PostgreSQL (auto-configured by Railway)
DATABASE_URL=postgresql://postgres:password@host:port/database

# Optional: Discord server/channel restrictions
GUILD_ID=your_server_id
CHANNEL_ID=your_channel_id
```

### **Step 5: Set Start Command**
In Railway settings, set **Start Command**:
```bash
python main.py
```

### **Step 6: Deploy**
1. Push changes to GitHub
2. Railway automatically deploys
3. Bot runs 24/7 with PostgreSQL

## **Local Development with Railway PostgreSQL**

### Connect to Railway Database Locally:
```bash
# Get DATABASE_URL from Railway dashboard
export DATABASE_URL="postgresql://postgres:password@host:port/database"

# Run bot locally with Railway database
python main.py
```

### Test Database Connection:
```bash
# Test PostgreSQL connection
python -m mkw_stats.database
```

## **Free Tier Limits**
- **PostgreSQL**: 500MB storage (thousands of players)
- **Bot Hosting**: $5 monthly credit (covers small bot)
- **Bandwidth**: 100GB/month
- **Uptime**: 24/7 with no sleep

## **Production Ready Features**
- ✅ Automatic SSL/TLS
- ✅ Connection pooling
- ✅ Automatic backups
- ✅ Environment variable management
- ✅ Git-based deployment
- ✅ Monitoring dashboard

## **Cost Estimation**
- **Free tier**: $0/month (500MB PostgreSQL + $5 credit)
- **Paid**: ~$5-10/month if you exceed free limits
- **Much cheaper than AWS/GCP** for small projects

## **Resume Benefits**
- ✅ Cloud deployment experience
- ✅ PostgreSQL production database
- ✅ CI/CD with Git integration
- ✅ Environment management
- ✅ 24/7 service reliability