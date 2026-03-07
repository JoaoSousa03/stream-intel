# Google OAuth Setup Guide

This StreamIntel application now supports Google OAuth authentication in addition to username/password authentication.

## Prerequisites

- A Google Cloud project with OAuth 2.0 credentials
- Client ID and Client Secret from Google Cloud Console

## Setup Instructions

### 1. Create Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to "APIs & Services" → "Credentials"
4. Click "Create Credentials" → "OAuth client ID"
5. Choose "Web application" as the application type
6. Add authorized redirect URIs:
   - For development: `http://localhost:5000/api/auth/google-callback`
   - For production: `https://yourdomain.com/api/auth/google-callback`
7. Click "Create" and copy your Client ID and Client Secret

### 2. Configure Environment Variables

Create a `.env` file in your project root with:

```
GOOGLE_CLIENT_ID=your-client-id-here
GOOGLE_CLIENT_SECRET=your-client-secret-here
GOOGLE_REDIRECT_URI=http://localhost:5000/api/auth/google-callback
SECRET_KEY=your-secret-key-here
```

For production, also set:
```
GOOGLE_REDIRECT_URI=https://yourdomain.com/api/auth/google-callback
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

Or manually install the new dependency:
```bash
pip install httpx
```

### 4. Run the Application

```bash
python run.py
```

The application will now show both:
- Traditional username/password login
- Google Sign-In button

## Usage

### First User
The very first user can register with either:
- Google OAuth (recommended)
- Username and password

### Additional Users
After the first user is created, additional users can only be added by:
- Signing in with Google (creates account automatically)
- Being added by an existing admin through username/password

## Authentication Flow

### Google OAuth Flow:
1. User clicks "Sign in with Google"
2. User is redirected to Google's login page
3. After authentication, user is redirected back with an authorization code
4. Backend exchanges code for access token
5. Backend retrieves user info (ID, email, name) from Google
6. User is created or logged in, and a session token is issued
7. User is redirected to the app with the token

### Traditional Login Flow:
1. User enters username and password
2. Backend validates credentials
3. Session token is issued
4. User is logged in

## Database Changes

The `users` table now includes:
- `google_id` - Unique Google user identifier
- `email` - User email
- `auth_type` - Either "password" or "google"
- `password_hash` - Made optional (NULL for OAuth users)
- `username` - Made optional for OAuth users

## Troubleshooting

### "Google OAuth not configured"
- Ensure `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set in environment variables
- Check your `.env` file is in the project root and readable

### "OAuth failed" error
- Verify your Client Secret is correct
- Check that the redirect URI matches exactly (protocol, domain, path)
- Ensure your Google project is active

### Token issues
- Clear browser cookies and try again
- Check that `SECRET_KEY` is set (should be a long random string for production)
- Verify the database file exists and is writable

## Security Considerations

- Always use HTTPS in production
- Set a strong `SECRET_KEY` (use `secrets.token_urlsafe(32)` to generate one)
- Keep Client Secret confidential (never commit to version control)
- Regularly rotate credentials if compromised
- The `si_token` cookie is `HttpOnly` and `SameSite=Lax` for security
