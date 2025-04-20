# ganglion

Ganglion is an application which serves [Textual](https://textual.textualize.io/) apps on the web.


## Compatibility

Tested on Linux / macOS. It may well run on Windows, but this is as yet untested.

## Installing

Ganglion is best installed as a standalone app.

The easiest way of doing this is with [uv](https://docs.astral.sh/uv/):

```
uv tool ganglion
```

You should find the `ganglion` command on your path. Confirm the installation was successful by running:

```
ganglion
```

### Setting up the database

Run the following to create a database:

```
ganglion initdb
```

This will create a sqllite database "ganglion.db" in the current directory.

## Serving

To run a Ganglion server, enter the following command:

```
ganglion serve
```

You can also add `DEBUG=1` when running locally to see prettier and more verbose logs:

```
DEBUG=1 ganglion serve
```

You can run a test client (for debugging) with the following command:

```
ganglion client
```


## Clients

To serve a Textual web app or apps install [textual-web](https://github.com/textualize/textual-web).
Follow the instructions on the textual-web repository to run apps, but add `-e local` to connect to a local server.

For example, so serve the Textual demo you could run the following:

```
textual-web -r "python -m textual" -e local
```


## Configuration

You can configure Ganglion via a TOML configuration file.
The path to this configuration file may be set in the env var `GANGLION_CONFIG`, or with the `--config` in the serve command (and others).

Here's the default, internal configuration:

```TOML
[server]
# The base URL where ganglion serves from
base_url = "http://127.0.0.1:8080"
# The URL for applications
app_url_format = "http://127.0.0.1:8080/{account}/{application}"
# The websocket URL where applications are served from
app_websocket_url = "ws://127.0.0.1:8080"

[templates]
# Root directory for templates
root = "${GANGLION_DATA}/templates"

[static]
# Local directory where static assets are contained
root = "${GANGLION_DATA}/static"
# URL where static assets are served from
url = "/static/"

[db]
# sqlalchemy async database URL
url = "sqlite+aiosqlite:///./ganglion.db"
# Consider Postgres for production
#url = "postgresql+asyncpg://postgres:password@localhost/ganglion"
```

If you want to edit this configuration, copy it to "ganglion.toml" and run with the following command:

```
GANGLION_CONFIG=./ganglion.toml ganglion serve 
```

Alternatively, use the `--config` switch to set the configuration path:

```
ganglion serve --config ./ganglion.toml
```

