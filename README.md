## Environment Setup

```bash
pip install -r requirements.txt
# or, pip3 install -r requirements
```

## Usage

```bash
export FLASK_DEBUG=1 # must be set; otherwise internal stack trace will not be printed
flask run [-p/--port <PORT>] --host 0.0.0.0 # change to 127.0.0.1 if put behind an Nginx server
```

or, 

```bash
python app.py
# or, python3 app.py
```

The service runs on port 5000 by default. For security purposes, it is recommended to put the service behind an Nginx reverse proxy with `proxy_pass` enabled.

## API

| URL PATH              | Method | Description                                                  |
| --------------------- | ------ | ------------------------------------------------------------ |
| /uploads/check        | GET    | Renders a simple webpage for uploading zip file, as defined in `templates/upload.html`. |
| /uploads/nocheck      | GET    | Same as above.                                               |
| /uploads/check        | POST   | Uploads a zip file and performs all checking.<br />If any check fails, renders an error page with stack trace; <br />Otherwise, redirect to the download URL for the output (zipped) folder. |
| /uploads/nocheck      | POST   | Similar to above, but no checking will be performed.<br />The error page is only rendered if an internal error is captured. |
| /downloads/\<filename\> | GET    | Downloads an output (zipped) folder<br />Users are redirected here upon uploading a zip file (and all checks are passed) |

## Config

Configurations are specified, in json format, in `config.json`. To override the default location of configs, set a `TEMPLATE_FILLER_CONFIG` environment variable, e.g.,

```bash
export TEMPLATE_FILLER_CONFIG="/tmp/config.json"
```

The following options are specified in config:

| Keys               | Values                                                       | Type   |
| ------------------ | ------------------------------------------------------------ | ------ |
| ZIP_DIR            | folder to save all uploaded zip files                        | string |
| EXTRACTED_DIR      | folder for extracting zip files and generating output        | string |
| DOWNLOAD_DIR       | folder for saving generated output (zip files) and downloading | string |
| MAX_CONTENT_LENGTH | maximum length for upload files, in bytes (B)                | number |