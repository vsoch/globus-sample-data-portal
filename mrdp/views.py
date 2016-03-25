import datetime
import uuid

from flask import (flash, g, redirect, render_template, request,
                   session, url_for)
from oauth2client import client as oauth
import requests

from globus_sdk import TransferClient

from mrdp import app, database
from mrdp.decorators import authenticated
from mrdp.utils import basic_auth_header


#
# Some dummy data for testing
#


test_datasets = [
    {'name': 'Dataset one', 'uri': str(uuid.uuid4())},
    {'name': 'Dataset two', 'uri': str(uuid.uuid4())},
    {'name': 'Dataset three', 'uri': str(uuid.uuid4())},
    {'name': 'Dataset four', 'uri': str(uuid.uuid4())},
    {'name': 'Dataset five', 'uri': str(uuid.uuid4())},
    {'name': 'Dataset six', 'uri': str(uuid.uuid4())},
    {'name': 'Dataset seven', 'uri': str(uuid.uuid4())},
]

test_task_id = str(uuid.uuid4())

test_file_list = [
    {'name': 'File Number One', 'size': 213514, 'uri': str(uuid.uuid4())},
    {'name': 'File Number two', 'size': 123525, 'uri': str(uuid.uuid4())},
    {'name': 'File Number three', 'size': 21343, 'uri': str(uuid.uuid4())},
    {'name': 'File Number four', 'size': 234235, 'uri': str(uuid.uuid4())},
    {'name': 'File Number five', 'size': 90835, 'uri': str(uuid.uuid4())},
    {'name': 'File Number six', 'size': 28722, 'uri': str(uuid.uuid4())},
    {'name': 'File Number seven', 'size': 765324, 'uri': str(uuid.uuid4())},
]

test_transfer_status = {
    'source_ep_name': 'XSEDE Keeneland',
    'dest_ep_name': 'UChicago RCC Midway',
    'request_time': datetime.datetime.now() - datetime.timedelta(days=1),
    'status': 'ACTIVE',
    'files_transferred': 2354,
    'faults': 0
}


#
# Add all MRDP application code below
#

@app.route('/', methods=['GET'])
def home():
    """Home page - play with it if you must!"""
    return render_template('home.jinja2')


@app.route('/login', methods=['GET'])
def login():
    """
    Add code here to:

    - Redirect user to Globus Auth
    - Get an access token and a refresh token
    - Store these tokens in the session
    - Redirect to the repository page or profile page
      if this is the first login
    """
    return redirect(url_for("authcallback"))


@app.route('/logout', methods=['GET'])
@authenticated
def logout():
    """
    Add code here to:

    - Destroy Globus Auth token (remove it from session?)
    - ???
    """
    headers = {'Authorization': basic_auth_header()}
    data = {
        'token_type_hint': 'refresh',
        'token': g.credentials.refresh_token
    }

    # Invalidate the tokens with Globus Auth
    requests.post(app.config['GA_REVOKE_URI'],
                  headers=headers,
                  data=data)

    # Destroy the session state
    session.clear()

    redirect_uri = url_for('home', _external=True)

    ga_logout_url = []
    ga_logout_url.append(app.config['GA_LOGOUT_URI'])
    ga_logout_url.append('?client={}'.format(app.config['GA_CLIENT_ID']))
    ga_logout_url.append('&redirect_uri={}'.format(redirect_uri))
    ga_logout_url.append('&redirect_name=MRDP Demo App')

    # Send the user to the Globus Auth logout page
    return redirect(''.join(ga_logout_url))


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    """User profile information. Assocated with a Globus Auth identity."""
    if request.method == 'GET':
        if session.get('is_authenticated'):
            identity_id = session.get('primary_identity')
            profile = database.load_profile(identity_id)

            if profile:
                name, email, project = profile

                session['name'] = name
                session['email'] = email
                session['project'] = project

        return render_template('profile.jinja2')
    elif request.method == 'POST':
        name = session['name'] = request.form['name']
        email = session['email'] = request.form['email']
        project = session['project'] = request.form['project']

        if session.get('is_authenticated'):
            database.save_profile(identity_id=session['primary_identity'],
                                  name=name,
                                  email=email,
                                  project=project)

            session['has_profile'] = True

            return redirect(url_for('profile'))
        else:
            return redirect(url_for('login'))


@app.route('/authcallback', methods=['GET'])
def authcallback():
    if 'error' in request.args:
        pass
        # handle error

    scopes = 'urn:globus:auth:scope:transfer.api.globus.org:all'
    config = app.config
    flow = oauth.OAuth2WebServerFlow(app.config['GA_CLIENT_ID'],
                                     scope=scopes,
                                     authorization_header=basic_auth_header(),
                                     redirect_uri=config['GA_REDIRECT_URI'],
                                     auth_uri=config['GA_AUTH_URI'],
                                     token_uri=config['GA_TOKEN_URI'],
                                     revoke_uri=config['GA_REVOKE_URI'])

    if 'code' in request.args:
        passed_state = request.args.get('state')

        if passed_state and passed_state == session.get('oauth2_state'):
            code = request.args.get('code')

            try:
                credentials = flow.step2_exchange(code)
            except Exception as err:
                return repr(err)
            else:
                session.pop('oauth2_state')

                id_token = credentials.id_token
                session.update(
                    credentials=credentials.to_json(),
                    is_authenticated=True,
                    primary_username=id_token.get('preferred_username'),
                    primary_identity=id_token.get('sub'),
                )

                # debug
                print(credentials.access_token)
                print(session)
            return redirect(url_for('repository'))
    else:
        state = str(uuid.uuid4())

        auth_uri = flow.step1_get_authorize_url(state=state)

        session['oauth2_state'] = state

        return redirect(auth_uri)

    return 'so sad'


@app.route('/repository', methods=['GET'])
@authenticated
def repository():
    """
    Add code here to:

    - Check that we have an authenticated user (i.e. don't allow
      unauthenticated users to access the repository)
    - Get a list of the datasets in the repository
    - Display a dataset list so user can browse/select to download

    The target template (repository.jinja2) expects 'datasets'
    (list of dictionaries) that describe each dataset as:
    {'name': 'dataset name', 'uri': 'dataset uri/path'}

    If you want to display additional information about each
    dataset, you must add those keys to the dictionary
    and modify the repository.jinja2 template accordingly.
    """

    return render_template('repository.jinja2', datasets=test_datasets)


@app.route('/download', methods=['POST'])
@authenticated
def download():
    """
    Add code here to:

    - Send to Globus to select a destination endpoint
    - Submit a Globus transfer request and get the task ID
    - Return to a transfer "status" page

    The target template expects a 'task_id' (str) and a
    'transfer_status' (dictionary) containing various details about the
    task. Since this route is called only once after a transfer request
    is submitted, it only provides a 'task_id'.
    """
    # Get a list of the selected datasets
    # e.g. datasets = request.form.getlist('dataset')

    # Get the selected year to filter the dataset
    # e.g. year_filter = request.form.get('year_filter')

    task_id = 'c726c69e-efa3-11e5-9831-22000b9da45e'
    flash(task_id)

    return(redirect(url_for('transfer_status', task_id=task_id)))


@app.route('/browse/<target_uri>', methods=['GET'])
@authenticated
def browse(target_uri):
    """
    Add code here to:

    - Get list of files for the selected dataset
    - Return a list of files to a browse view

    The target template (browse.jinja2) expects a unique dataset
    identifier 'dataset_uri' (str) and 'file_list' (list of
    dictionaries) containing the following information about each file
    in the dataset:

    {'name': 'file name', 'size': 'file size', 'uri': 'file uri/path'}

    'dataset_uri' is passed to the route in the URL as 'target_uri'.

    If you want to display additional information about each file, you
    must add those keys to the dictionary and modify the browse.jinja2
    template accordingly.
    """

    return render_template('browse.jinja2', dataset_uri=target_uri,
                           file_list=test_file_list)


@app.route('/status/<task_id>', methods=['GET'])
@authenticated
def transfer_status(task_id):
    """
    Add code here to call Globus to get status/details of transfer with
    task_id.

    The target template (tranfer_status.jinja2) expects a 'task_id'
    (str) and a 'transfer_status' (dictionary) containing various
    details about the task. 'transfer_status' is expected to contain the
    following keys:

    {
        'source_ep_name': 'display name of source endpoint',
        'dest_ep_name': 'display name of destination endpoint',
        'request_time': time that the transfer request was submitted,
        'status': 'status of the transfer task',
        'files_transferred': number of files transferred so far,
        'fault': number of faults encountered,
    }

    'task_id' is passed to the route in the URL as 'task_id'.

    If you want to display additional information about the transfer,
    you must add those keys to the dictionary and modify the
    transfer_status.jinja2 template accordingly.
    """
    transfer = TransferClient(auth_token=g.credentials.access_token)
    task = transfer.get_task(task_id)

    return render_template('transfer_status.jinja2', task=task.data)
