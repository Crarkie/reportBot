from sanic import Sanic
from sanic_cors import CORS
from config import Config

app = Sanic(__name__)
app.config.from_object(Config)
CORS(app)