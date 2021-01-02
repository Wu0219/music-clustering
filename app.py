import spotipy
import os
import spotipy.util as util
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
import altair as alt
from sklearn.preprocessing import MinMaxScaler
import plotly.graph_objects as go
from kneed import KneeLocator
import streamlit as st
from math import sqrt
from matplotlib import cm
import SessionState
from spotipy.oauth2 import SpotifyClientCredentials
import requests

session_state = SessionState.get(checkboxed=False)

def main():
    flag = False
    num_playlists = st.sidebar.number_input('How many playlists would you like to cluster?', 1, 5, 2)
    playlists = playlist_user_input(num_playlists)
    if st.button("Run Algorithm") or session_state.checkboxed:
        session_state.checkboxed = True
        print(playlists)
        df = concatenate_playlists(playlists)
        if df is None:
            st.warning("One of your playlist URIs was not entered properly")
            st.stop()
        else:
            st.write(df)


    # if st.button("Run Algorithm"):
            # x_axis = list(df['name'])
            # y_axis = st.selectbox("Choose a variable for the y-axis", list(df.columns)[3:], index=2)
            # visualize_data(df, x_axis, y_axis)
            clustered_df, n_clusters = kmeans(df)
            visualize_clusters(clustered_df, n_clusters)
            
            cluster_labels = clustered_df['Cluster']
            orig = clustered_df.drop(columns=['Cluster', "Component 1", "Component 2"])
            norm_df = make_normalized_df(orig, 4)
            norm_df.insert(4, 'cluster', cluster_labels)
            fig = make_radar_chart(norm_df, n_clusters)
            st.write(fig)

            metadata_df = clustered_df[clustered_df.columns[:4]]
            metadata_df.insert(2, 'cluster', cluster_labels)
            keys = sorted(list(metadata_df["cluster"].unique()))
            cluster = st.selectbox("Choose a cluster to preview and/or export tracks", keys, index=0)
            preview_cluster_playlist(metadata_df, cluster)
    else:
        pass

def playlist_user_input(num_playlists):
    playlists = []
    defaults = ["spotify:playlist:4ZvKulfjQx6Xi0Pxm6tlC2", "spotify:playlist:7iAkkvQ11nmfS1Rv1N5YYr", "spotify:playlist:6hQBKDy8WTuf0lHEKgEnZo"]
    for i in range(num_playlists):
        playlists.append(st.sidebar.text_input("Playlist URI " + str(i+1)))
    return playlists

@st.cache(allow_output_mutation=True)
def concatenate_playlists(playlists):
    df = pd.DataFrame(columns=['name', 'artist', 'track_URI', 'playlist', 'acousticness', 'danceability', 'energy', 'instrumentalness', 'liveness', 'loudness', 'speechiness', 'tempo', 'valence'])
    if all(playlists):
        for playlist_uri in playlists:
            df = get_features_for_playlist(df, os.environ.get('USERNAME'), playlist_uri)
        return df
    else:
        return None



# Get Spotipy credentials from config
def load_config():
    stream = open('config.yaml')
    user_config = yaml.load(stream, Loader=yaml.FullLoader)
    return user_config

# @st.cache(allow_output_mutation=True)
def get_token():
    print("generating token")
    token = util.prompt_for_user_token( 
        scope='playlist-read-private', 
        client_id=os.environ.get('CLIENT_ID'), 
        client_secret=os.environ.get('CLIENT_SECRET'), 
        redirect_uri=os.environ.get('REDIRECT_URI'),
        show_dialog=True)
    sp = spotipy.Spotify(auth=token)
    # print(os.environ.get('CLIENT_ID'))
    # auth_manager = spotipy.oauth2.SpotifyOAuth(scope='playlist-read-private playlist-modify-public', 
        # client_id=os.environ.get('CLIENT_ID'), 
        # client_secret=os.environ.get('CLIENT_SECRET'), 
        # redirect_uri=os.environ.get('REDIRECT_URI'),
        # show_dialog=True)
    
    # if not auth_manager.get_cached_token():
    # # auth_manager.get_access_token(as_dict=False, check_cache=True)
    #     auth_url = auth_manager.get_authorize_url()
    #     # print(auth_url)
    #     res = requests.get(auth_url)
    #     # print(res.url)
        # code = auth_manager.parse_response_code(res.url)
        # print(code)
        # print(auth_url)
    # # html_string = f'<h2><a href="{auth_url}">Sign in</a></h2>'
    # # st.markdown(html_string, unsafe_allow_html=True)
        # res = requests.get(auth_url)
    #     # print(res)
    # sp =  spotipy.Spotify(auth_manager=auth_manager)
    # me = sp.me()
    # pprint(me)
    st.markdown(f'<h2>Hi {sp.me()["display_name"]} 👋</h2>', unsafe_allow_html=True)
    return sp

# A function to extract track names and URIs from a playlist
def get_playlist_info(username, playlist_uri):
    # initialize vars
    offset = 0
    tracks, uris, names, artists = [], [], [], []

    # get playlist id and name from URI
    playlist_id = playlist_uri.split(':')[2]
    playlist_name = sp.user_playlist(username, playlist_id)['name']

    # get all tracks in given playlist (max limit is 100 at a time --> use offset)
    while True:
        results = sp.user_playlist_tracks(username, playlist_id, offset=offset)
        tracks += results['items']
        if results['next'] is not None:
            offset += 100
        else:
            break
        
    # get track metadata
    for track in tracks:
        names.append(track['track']['name'])
        artists.append(track['track']['artists'][0]['name'])
        uris.append(track['track']['uri'])
    
    return playlist_name, names, artists, uris

@st.cache(allow_output_mutation=True)
def get_features_for_playlist(df, username, uri):
    # get all track metadata from given playlist
    playlist_name, names, artists, uris = get_playlist_info(username, uri)
    
    # iterate through each track to get audio features and save data into dataframe
    for name, artist, track_uri in zip(names, artists, uris):
        
        # access audio features for given track URI via spotipy 
        audio_features = sp.audio_features(track_uri)

        # get relevant audio features
        feature_subset = [audio_features[0][col] for col in df.columns if col not in ["name", "artist", "track_URI", "playlist"]]

        # compose a row of the dataframe by flattening the list of audio features
        row = [name, artist, track_uri, playlist_name, *feature_subset]
        df.loc[len(df.index)] = row
    return df

def optimal_number_of_clusters(wcss):
    x1, y1 = 2, wcss[0]
    x2, y2 = 20, wcss[len(wcss)-1]

    distances = []
    for i in range(len(wcss)):
        x0 = i+2
        y0 = wcss[i]
        numerator = abs((y2-y1)*x0 - (x2-x1)*y0 + x2*y1 - y2*x1)
        denominator = sqrt((y2 - y1)**2 + (x2 - x1)**2)
        distances.append(numerator/denominator)
    
    return distances.index(max(distances)) + 1

def visualize_data(df, x_axis, y_axis):
    graph = alt.Chart(df.reset_index()).mark_bar().encode(
        x=alt.X('name', sort='y'),
        y=alt.Y(str(y_axis)+":Q"),
    ).interactive()

    st.altair_chart(graph, use_container_width=True)

def num_components_graph(ax, num_columns, evr):
    ax.plot(range(1, num_columns+1), evr.cumsum(), 'bo-')
    ax.set_title('Explained Variance by Components')
    ax.set(xlabel='Number of Components', ylabel='Cumulative Explained Variance')
    ax.hlines(0.8, xmin=1, xmax=num_columns, linestyles='dashed')
    return ax

def num_clusters_graph(ax, max_clusters, wcss):
    ax.plot([i for i in range(1, max_clusters)], wcss, 'bo-')
    ax.set_title('Optimal Number of Clusters')
    ax.set(xlabel='Number of Clusters [k]', ylabel='Within Cluster Sum of Squares (WCSS)')
    ax.vlines(KneeLocator([i for i in range(1, max_clusters)], wcss, curve='convex', direction='decreasing').knee, ymin=0, ymax=max(wcss), linestyles='dashed')
    return ax

@st.cache(allow_output_mutation=True)
def kmeans(df):
    print("got here")
    df_X = df.drop(columns=df.columns[:4])
    print("Standard scaler and PCA")
    scaler = StandardScaler()
    X_std = scaler.fit_transform(df_X) 
    pca = PCA()
    pca.fit(X_std)
    evr = pca.explained_variance_ratio_
    for i, exp_var in enumerate(evr.cumsum()):
        if exp_var >= 0.8:
            n_comps = i + 1
            break
    print("Finding optimal number of components", n_comps)
    pca = PCA(n_components=n_comps)
    pca.fit(X_std)
    scores_pca = pca.transform(X_std)
    wcss = []
    max_clusters = 11
    for i in range(1, max_clusters):
        kmeans_pca = KMeans(i, init='k-means++', random_state=42)
        kmeans_pca.fit(scores_pca)
        wcss.append(kmeans_pca.inertia_)
    n_clusters = KneeLocator([i for i in range(1, max_clusters)], wcss, curve='convex', direction='decreasing').knee
    print("Finding optimal number of clusters", n_clusters)
    # fig, (ax1, ax2) = plt.subplots(1, 2)
    # ax1 = num_components_graph(ax1, len(df_X.columns), evr)
    # ax2 = num_clusters_graph(ax2, max_clusters, wcss)
    print("Performing KMeans")
    kmeans_pca = KMeans(n_clusters=n_clusters, init='k-means++', random_state=42)
    kmeans_pca.fit(scores_pca)
    df_seg_pca_kmeans = pd.concat([df_X.reset_index(drop=True), pd.DataFrame(scores_pca)], axis=1)
    df_seg_pca_kmeans.columns.values[(-1 * n_comps):] = ["Component " + str(i+1) for i in range(n_comps)]
    df_seg_pca_kmeans['Cluster'] = kmeans_pca.labels_
    df['Cluster'] = df_seg_pca_kmeans['Cluster']
    df['Component 1'] = df_seg_pca_kmeans['Component 1']
    df['Component 2'] = df_seg_pca_kmeans['Component 2']
    # fig.tight_layout()
    return df, n_clusters

def get_color_range(n_clusters):
    cmap = cm.get_cmap('tab20b')    
    range_ = []
    for i in range(n_clusters):
        color = 'rgb('
        mapped = cmap(i/n_clusters)
        for j in range(3):
            color += str(int(mapped[j] * 255))
            if j != 2:
                color += ", "
            else:
                color += ")"
        range_.append(color)
    return range_

def visualize_clusters(df, n_clusters):
    range_ = get_color_range(n_clusters)
    graph = alt.Chart(df.reset_index()).mark_point(filled=True, size=60).encode(
        x=alt.X('Component 2'),
        y=alt.Y('Component 1'),
        shape=alt.Shape('playlist:N', scale=alt.Scale(range=["circle", "diamond", "square", "triangle-down", "triangle-up"])),
        color=alt.Color('Cluster', scale=alt.Scale(domain=[i for i in range(n_clusters)], range=range_)),
        tooltip=['name', 'artist']
    ).interactive()
    st.altair_chart(graph, use_container_width=True)

def make_normalized_df(df, col_sep):
    non_features = df[df.columns[:col_sep]]
    features = df[df.columns[col_sep:]]
    norm = MinMaxScaler().fit_transform(features)
    scaled = pd.DataFrame(norm, index=df.index, columns = df.columns[col_sep:])
    return pd.concat([non_features, scaled], axis=1)

def make_radar_chart(norm_df, n_clusters):
    fig = go.Figure()
    cmap = cm.get_cmap('tab20b')
    angles = list(norm_df.columns[5:])
    angles.append(angles[0])

    layoutdict = dict(
                radialaxis=dict(
                visible=True,
                range=[0, 1]
                ))

    for i in range(n_clusters):
        subset = norm_df[norm_df['cluster'] == i]
        data = [np.mean(subset[col]) for col in subset.columns[5:]]
        data.append(data[0])
        fig.add_trace(go.Scatterpolar(
            r=data,
            theta=angles,
            # fill='toself',
            # fillcolor = 'rgba' + str(cmap(i/n_clusters)),
            mode='lines',
            line_color='rgba' + str(cmap(i/n_clusters)),
            name="Cluster " + str(i)))
        
    fig.update_layout(
            polar=layoutdict,
            showlegend=True
    )
    fig.update_traces()
    return fig

def preview_cluster_playlist(df, cluster):
    df = df[df['cluster'] == cluster]
    st.write(df)
    if st.button("Export to playlist"):
        result = sp.user_playlist_create(user_config['username'], 'cluster'+str(cluster), public=True, collaborative=False, description='')
        playlist_id = result['id']
        songs = list(df.loc[df['cluster'] == cluster]['track_URI'])
        if len(songs) > 100:
            sp.playlist_add_items(playlist_id, songs[:100])
            sp.playlist_add_items(playlist_id, songs[100:])
        else:
            sp.playlist_add_items(playlist_id, songs)
    else:
        pass

if __name__ == "__main__":
    # user_config = load_config()
    
    # Initialize Spotify API token
    sp = get_token()
    # client_credentials_manager = SpotifyClientCredentials(client_id=os.environ.get('CLIENT_ID'), client_secret=os.environ.get('CLIENT_SECRET'))
    # sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

    
    main()