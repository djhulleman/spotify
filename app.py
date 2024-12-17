import os
import requests
from flask import Flask, request, redirect, session, url_for, render_template
from dotenv import load_dotenv
import random
import json

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app and secret key
app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secret key for Flask session

# Spotify API credentials from .env file
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')

# Helper function to handle API requests and error handling
def api_request(url, headers, params=None):
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()  # Will raise an HTTPError for bad responses
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"Error during API request to {url}: {e}")
        return None

# Home route
@app.route('/')
def home():
    """Home route that displays a 'Login with Spotify' button."""
    return render_template('home.html')

# Login route (Redirect to Spotify authorization page)
@app.route('/login')
def login():
    """Redirect the user to Spotify's authorization page."""
    spotify_auth_url = (
        "https://accounts.spotify.com/authorize?"
        f"response_type=code&client_id={SPOTIFY_CLIENT_ID}"
        f"&redirect_uri={SPOTIFY_REDIRECT_URI}"
        f"&scope=user-read-private%20user-top-read"
    )
    return redirect(spotify_auth_url)

# Callback route (Handle Spotify's redirect after user authorizes the app)
@app.route('/callback')
def callback():
    """Handles Spotify's redirect after user authorizes the app."""
    code = request.args.get('code')
    token_url = "https://accounts.spotify.com/api/token"
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': SPOTIFY_REDIRECT_URI,
        'client_id': SPOTIFY_CLIENT_ID,
        'client_secret': SPOTIFY_CLIENT_SECRET
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    response = requests.post(token_url, data=payload, headers=headers)
    if response.status_code != 200:
        return f"Error fetching access token: {response.text}"

    token_info = response.json()
    session['access_token'] = token_info.get('access_token')
    session['refresh_token'] = token_info.get('refresh_token')

    return redirect(url_for('profile'))  # Redirect to profile route

# Profile route (Fetch user data and top artists/tracks)
@app.route('/profile')
def profile():
    """Get the user's Spotify profile information using the access token."""
    access_token = session.get('access_token')

    if not access_token:
        return redirect(url_for('login'))  # If no token, redirect to login

    headers = {'Authorization': f'Bearer {access_token}'}

    # Fetch user profile
    user_data = api_request("https://api.spotify.com/v1/me", headers)
    if not user_data:
        return "Error fetching user profile."

    # Fetch top artists
    top_artists_data = api_request("https://api.spotify.com/v1/me/top/artists", headers)
    if not top_artists_data:
        return "Error fetching top artists."

    # Fetch top tracks
    top_tracks_data = api_request("https://api.spotify.com/v1/me/top/tracks", headers)
    if not top_tracks_data:
        return "Error fetching top tracks."

    return render_template('profile.html', user_data=user_data, top_artists=top_artists_data, top_tracks=top_tracks_data)

# Logout route (Clear session and log user out)
@app.route('/logout')
def logout():
    """Clear the session and log the user out."""
    session.clear()
    return redirect(url_for('home'))

# Fetch similar artists based on artist ID
def get_similar_artists(artist_id, access_token):
    url = f"https://api.spotify.com/v1/artists/{artist_id}/related-artists"
    headers = {'Authorization': f'Bearer {access_token}'}
    similar_artists_data = api_request(url, headers)
    return similar_artists_data.get('artists', []) if similar_artists_data else []

# Fetch hidden gems based on genre
def get_hidden_gems(genre, access_token, max_results=5):
    search_url = f"https://api.spotify.com/v1/recommendations?seed_genres={genre}&limit=50"
    headers = {'Authorization': f'Bearer {access_token}'}
    recommendations_data = api_request(search_url, headers)
    
    if not recommendations_data:
        return []

    tracks = [
        {
            'name': track['name'],
            'artist': track['artists'][0]['name'],
            'popularity': track['popularity'],
            'preview_url': track['preview_url'],
            'album': track['album']['name']
        }
        for track in recommendations_data['tracks']
        if track['popularity'] < 50  # Only include less mainstream tracks
    ]
    return tracks[:max_results]

# Recommend music based on user data
def recommend_music(user_data, access_token):
    recommended_tracks = []
    top_artists = user_data.get('top_artists', [])

    # Step 1: Recommend similar artists based on the user's top artists
    for artist in top_artists:
        similar_artists = get_similar_artists(artist['id'], access_token)
        recommended_tracks.extend({
            'name': similar_artist['name'],
            'type': 'Artist',
            'genres': similar_artist['genres'],
            'popularity': similar_artist['popularity']
        } for similar_artist in similar_artists)

    # Step 2: Recommend hidden gems based on user's favorite genre
    if 'genres' in user_data:
        for genre in user_data['genres']:
            hidden_gems = get_hidden_gems(genre, access_token)
            recommended_tracks.extend({
                'name': track['name'],
                'type': 'Track',
                'artist': track['artist'],
                'album': track['album'],
                'popularity': track['popularity'],
                'preview_url': track['preview_url']
            } for track in hidden_gems)

    random.shuffle(recommended_tracks)
    return recommended_tracks[:10]  # Return top 10 recommendations

# Recommendations route (Get music recommendations for the user)
@app.route('/recommend')
def recommend():
    """Get music recommendations for the user."""
    access_token = session.get('access_token')

    if not access_token:
        return redirect(url_for('login'))  # Redirect to login if no token found

    # Fetch user profile and top artists
    headers = {'Authorization': f'Bearer {access_token}'}
    user_data = api_request("https://api.spotify.com/v1/me", headers)
    if not user_data:
        return "Error fetching user profile."

    top_artists_data = api_request("https://api.spotify.com/v1/me/top/artists", headers)
    if not top_artists_data:
        return "Error fetching top artists."

    user_data['top_artists'] = top_artists_data['items']

    similar_artists = []
    for i in range(len(user_data)):
        similar_artist = get_similar_artists(user_data['top_artists'], access_token)
        similar_artists.append(similar_artist)

    # Get recommendations
    recommended_tracks = recommend_music(user_data, access_token)

    # Render the recommendations page with recommended tracks
    return render_template('recommendations.html', tracks=recommended_tracks)

if __name__ == '__main__':
    app.run(debug=True)
