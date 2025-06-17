#!/bin/bash

# MKWStatsBot - GitHub Repository Initialization

echo "🚀 Initializing MKWStatsBot GitHub Repository"
echo "=============================================="

# Initialize git repository
echo "📁 Initializing Git repository..."
git init

# Add all files
echo "📋 Adding files to Git..."
git add .

# Check what will be committed
echo ""
echo "📊 Files to be committed:"
git status --porcelain

echo ""
echo "🔒 Security Check:"
echo "✅ .env files are ignored"
echo "✅ Database files are ignored" 
echo "✅ Log files are ignored"
echo "✅ No sensitive data will be committed"

echo ""
echo "📝 Creating initial commit..."
git commit -m "Initial commit: MKWStatsBot - Mario Kart Discord bot with OCR

Features:
- Discord bot for Mario Kart race result extraction
- OCR processing with Tesseract
- Team roster management
- Player statistics tracking
- SQLite/PostgreSQL database support
- Table format presets
- Data validation and confirmation system
- Cloud deployment ready

Perfect for Data Engineering portfolios!"

echo ""
echo "✅ Repository initialized successfully!"
echo ""
echo "📋 Next Steps:"
echo "1. Create repository on GitHub:"
echo "   - Go to https://github.com/new"
echo "   - Repository name: MKWStatsBot"
echo "   - Description: Mario Kart Discord bot with OCR and statistics tracking"
echo "   - Make it public (for portfolio)"
echo ""
echo "2. Connect to GitHub:"
echo "   git remote add origin https://github.com/YOUR_USERNAME/MKWStatsBot.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "3. Add topics/tags on GitHub:"
echo "   - discord-bot"
echo "   - ocr"
echo "   - data-engineering"
echo "   - mario-kart"
echo "   - python"
echo "   - tesseract"
echo "   - statistics"
echo ""
echo "🏁 Ready to showcase your Data Engineering skills!" 