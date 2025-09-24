#!/bin/bash

# Exit on any error
set -e

echo "🚀 Starting deployment process..."

# Build the application
echo "📦 Building application..."
npm run build

# Check if build was successful
if [ ! -d "dist" ]; then
    echo "❌ Build failed - dist directory not found"
    exit 1
fi

# Define server path
SERVER_PATH="/var/www/crunchygherkins-app"

# Create backup of current deployment
echo "💾 Creating backup..."
if [ -d "$SERVER_PATH" ]; then
    sudo cp -r "$SERVER_PATH" "${SERVER_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
fi

# Clear the server directory (but preserve .htaccess if it exists)
echo "🧹 Clearing server directory..."
if [ -f "$SERVER_PATH/.htaccess" ]; then
    sudo cp "$SERVER_PATH/.htaccess" /tmp/.htaccess.backup
fi

sudo rm -rf "$SERVER_PATH"/*

# Copy new files
echo "📁 Copying new files..."
sudo cp -r dist/* "$SERVER_PATH/"

# Restore .htaccess if it existed
if [ -f "/tmp/.htaccess.backup" ]; then
    sudo cp /tmp/.htaccess.backup "$SERVER_PATH/.htaccess"
    rm /tmp/.htaccess.backup
fi

# Set proper permissions
echo "🔒 Setting permissions..."
sudo chown -R www-data:www-data "$SERVER_PATH"
sudo find "$SERVER_PATH" -type f -exec chmod 644 {} \;
sudo find "$SERVER_PATH" -type d -exec chmod 755 {} \;

# Add cache control headers (if .htaccess doesn't exist)
if [ ! -f "$SERVER_PATH/.htaccess" ]; then
    echo "📝 Creating .htaccess for cache control..."
    sudo tee "$SERVER_PATH/.htaccess" > /dev/null << 'EOF'
# Cache static assets for 1 year
<filesMatch "\.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$">
    ExpiresActive On
    ExpiresDefault "access plus 1 year"
    Header set Cache-Control "public, immutable"
</filesMatch>

# Don't cache HTML files
<filesMatch "\.(html)$">
    ExpiresActive On
    ExpiresDefault "access plus 0 seconds"
    Header set Cache-Control "no-cache, no-store, must-revalidate"
    Header set Pragma "no-cache"
    Header set Expires "0"
</filesMatch>

# Enable gzip compression
<IfModule mod_deflate.c>
    AddOutputFilterByType DEFLATE text/plain
    AddOutputFilterByType DEFLATE text/html
    AddOutputFilterByType DEFLATE text/xml
    AddOutputFilterByType DEFLATE text/css
    AddOutputFilterByType DEFLATE application/xml
    AddOutputFilterByType DEFLATE application/xhtml+xml
    AddOutputFilterByType DEFLATE application/rss+xml
    AddOutputFilterByType DEFLATE application/javascript
    AddOutputFilterByType DEFLATE application/x-javascript
</IfModule>

# Security headers
Header always set X-Frame-Options "SAMEORIGIN"
Header always set X-Content-Type-Options "nosniff"
Header always set Referrer-Policy "strict-origin-when-cross-origin"
EOF
    sudo chown www-data:www-data "$SERVER_PATH/.htaccess"
    sudo chmod 644 "$SERVER_PATH/.htaccess"
fi

# Restart nginx/apache to clear any server-side cache
echo "🔄 Restarting web server..."
if systemctl is-active --quiet nginx; then
    sudo systemctl reload nginx
elif systemctl is-active --quiet apache2; then
    sudo systemctl reload apache2
fi

# Display deployment info
echo "✅ Deployment completed successfully!"
echo "📊 Deployment summary:"
echo "   - Build time: $(date)"
echo "   - Files deployed: $(find $SERVER_PATH -type f | wc -l)"
echo "   - Total size: $(du -sh $SERVER_PATH | cut -f1)"

# Optional: Clear CloudFlare cache if you're using it
# echo "☁️ Clearing CloudFlare cache..."
# curl -X POST "https://api.cloudflare.com/client/v4/zones/YOUR_ZONE_ID/purge_cache" \
#      -H "Authorization: Bearer YOUR_API_TOKEN" \
#      -H "Content-Type: application/json" \
#      --data '{"purge_everything":true}'

echo "🎉 Done! Your app should be updated at https://app.crunchygherkins.com"