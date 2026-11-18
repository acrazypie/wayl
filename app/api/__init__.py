from flask_restful import Api

from app.api.auth import (
    ForgotPassword,
    Login,
    Logout,
    RefreshToken,
    Register,
    ResetPassword,
    SessionInfo,
)
from app.api.music import (
    ArtistDetail,
    ArtistSearch,
    FeedList,
    HistoryList,
    PlaylistDetail,
    PlaylistList,
    PlaylistSongDetail,
    SavedSongDetail,
    SavedSongList,
    SongDetail,
    SongSearch,
    Stats,
)
from app.api.user import (
    ChangePassword,
    FollowList,
    FollowUser,
    Me,
    UserListens,
    UserPlaylists,
    UserProfile,
    UserSearch,
)

api = Api()


def register_routes(app):
    # Resources must be added BEFORE init_app, otherwise Flask-RESTful never registers them.
    api.add_resource(SessionInfo, "/auth/session")
    api.add_resource(Register, "/auth/register")
    api.add_resource(Login, "/auth/login")
    api.add_resource(Logout, "/auth/logout")
    api.add_resource(ForgotPassword, "/auth/forgot")
    api.add_resource(ResetPassword, "/auth/reset")
    api.add_resource(RefreshToken, "/auth/refresh")

    api.add_resource(Me, "/api/me")
    api.add_resource(ChangePassword, "/api/me/password")
    api.add_resource(SavedSongList, "/api/me/songs")
    api.add_resource(SavedSongDetail, "/api/me/songs/<string:song_id>")
    api.add_resource(FollowList, "/api/me/following", endpoint="my_following",
                     resource_class_args=("following",))
    api.add_resource(FollowList, "/api/me/followers", endpoint="my_followers",
                     resource_class_args=("followers",))

    api.add_resource(UserSearch, "/api/users")
    api.add_resource(UserProfile, "/api/users/<int:user_id>")
    api.add_resource(UserListens, "/api/users/<int:user_id>/listens")
    api.add_resource(UserPlaylists, "/api/users/<int:user_id>/playlists")
    api.add_resource(FollowUser, "/api/users/<int:user_id>/follow")

    api.add_resource(SongSearch, "/api/songs")
    api.add_resource(SongDetail, "/api/songs/<string:song_id>")
    api.add_resource(ArtistSearch, "/api/artists")
    api.add_resource(ArtistDetail, "/api/artists/<string:artist_id>")

    api.add_resource(PlaylistList, "/api/playlists")
    api.add_resource(PlaylistDetail, "/api/playlists/<int:playlist_id>")
    api.add_resource(PlaylistSongDetail, "/api/playlists/<int:playlist_id>/songs/<string:song_id>")
    api.add_resource(HistoryList, "/api/history")
    api.add_resource(FeedList, "/api/feed")
    api.add_resource(Stats, "/api/stats")

    api.init_app(app)
