import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import difflib

# Spotify authentication
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id='SPOTIFY_CLIENT_ID',
    client_secret='SPOTIFY_CLIENT_SECRET',
    redirect_uri='http://localhost:8080',
    scope='playlist-modify-public',
    open_browser=False
))

# Print the Spotify authorization URL for the user to navigate to
auth_url = sp.auth_manager.get_authorize_url()
print("Please navigate to the following URL to authorize Spotify:")
print(auth_url)

# Prompt the user to enter the redirected URL after Spotify authorization
redirected_url = "http://localhost:8081"

# Extract the code from the redirected URL for Spotify
try:
    code = sp.auth_manager.parse_response_code("redirected_url")
    if not code:
        raise ValueError("Authorization code not found in the URL. Please check the URL and try again.")
    sp.auth_manager.get_access_token(code)
except Exception as e:
    print(f"An error occurred during Spotify authorization: {e}")
    exit()

# YouTube authentication using Google's OAuth 2.0 flow
CLIENT_SECRETS_FILE = "client_secrets.json"  # Replace with your client secrets file
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

# Create an OAuth 2.0 flow object for YouTube
flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
    CLIENT_SECRETS_FILE, SCOPES
)

# Run the OAuth flow and get credentials
credentials = flow.run_local_server(port=8081)  # Using a different port to avoid conflict

# Build the YouTube service
youtube = googleapiclient.discovery.build(
    "youtube", "v3", credentials=credentials
)

# Function to search for a song on Spotify and return the best match URI
def search_song_on_spotify(sp, song_name, artist_name):
    query = f"{song_name} {artist_name}"
    results = sp.search(q=query, type='track', limit=5)
    tracks = results['tracks']['items']

    if not tracks:
        print(f"No exact match found for '{song_name}' by '{artist_name}'. Trying a broader search...")
        results = sp.search(q=f"track:{song_name}", type='track', limit=5)
        tracks = results['tracks']['items']

    if tracks:
        best_match = None
        best_score = 0
        for track in tracks:
            track_name = track['name'].lower()
            track_artist_names = ', '.join([artist['name'] for artist in track['artists']])
            similarity_score = difflib.SequenceMatcher(None, f"{song_name.lower()} {artist_name.lower()}", f"{track_name} {track_artist_names.lower()}").ratio()

            if similarity_score > best_score:
                best_score = similarity_score
                best_match = track

        if best_match and best_score > 0.6:  # Adjust threshold as needed
            album_name = best_match.get('album', {}).get('name', 'Unknown Album')
            artist_names = ', '.join([artist['name'] for artist in best_match['artists']])
            print(f"Best match found: '{best_match['name']}' by '{artist_names}' from album '{album_name}' (Score: {best_score:.2f})")
            return best_match['uri']
        else:
            print(f"No sufficiently close match found for '{song_name}' by '{artist_name}' (Best score: {best_score:.2f})")
    else:
        print(f"No match found for '{song_name}' by '{artist_name}'.")

    return None

# Function to get all playlists created by the user
def get_all_user_playlists(sp):
    playlists = []
    offset = 0
    while True:
        response = sp.current_user_playlists(offset=offset)
        playlists.extend(response['items'])
        if len(response['items']) == 0:
            break
        offset += len(response['items'])
    return playlists

# Function to get all tracks from a specific playlist
def get_tracks_from_playlist(sp, playlist_id):
    tracks = []
    offset = 0
    while True:
        response = sp.playlist_tracks(playlist_id, offset=offset)
        tracks.extend(response['items'])
        if len(response['items']) == 0:
            break
        offset += len(response['items'])
    return tracks

# Get all playlists created by the user
user_playlists = get_all_user_playlists(sp)

# Iterate through each playlist and process each one
try:
    for playlist in user_playlists:
        print(f"\nProcessing playlist: {playlist['name']}")
        tracks = get_tracks_from_playlist(sp, playlist['id'])
        spotify_uris = []

        for item in tracks:
            track_info = item['track']
            song_title = track_info['name']
            artist_name = track_info['artists'][0]['name']
            print(f"Found song: '{song_title}' by '{artist_name}'")

            # Search for the song on Spotify
            uri = search_song_on_spotify(sp, song_title, artist_name)
            if uri:
                spotify_uris.append(uri)
            else:
                print(f"Song '{song_title}' by '{artist_name}' not found on Spotify.")

        # Create a new playlist for matched songs if any
        if spotify_uris:
            new_playlist_name = f"Matched - {playlist['name']}"
            new_playlist = sp.user_playlist_create(user=sp.me()['id'], name=new_playlist_name, public=True)
            new_playlist_id = new_playlist['id']

            # Add found songs to the new playlist in batches (Spotify limits items per request)
            batch_size = 100
            for i in range(0, len(spotify_uris), batch_size):
                sp.playlist_add_items(new_playlist_id, spotify_uris[i:i + batch_size])

            print(f"Successfully added {len(spotify_uris)} songs to the playlist '{new_playlist_name}'.")
        else:
            print(f"No songs found for playlist '{playlist['name']}'.")

    print("\nAll playlists have been processed.")
except Exception as e:
    print(f"An error occurred: {e}")