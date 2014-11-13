# -*- coding: utf-8 -*-

import os
import json
import base64
import requests
import urlparse
from multiprocessing import Process

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.forms import AuthenticationForm as authentication_form
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from furl import furl
import pymongo

from lib import jenkins
from lib import keygen as ssh_keygen
from lib import gerrit
from .models import Payload
from .models import Badge
from .models import Repo

BADGE_URL = settings.BADGE_URL
GERRIT_SSH_KEY_PATH = settings.GERRIT_SSH_KEY_PATH


@csrf_exempt
def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            return HttpResponseRedirect("/")
    else:
        form = UserCreationForm()
    return render(request, "core/register.html", {
        'form': form,
    })


def logout_view(request):
    logout(request)
    return HttpResponseRedirect('/')


@csrf_exempt
def login_view(request):
    """login view
    """
    redirect_to = request.POST.get('next', '/')

    if request.method == "POST":
        form = authentication_form(request, data=request.POST)
        if form.is_valid():

            # Okay, security check complete. Log the user in.
            login(request, form.get_user())

            return HttpResponseRedirect(redirect_to)
    else:
        form = authentication_form(request)

    return render(request, 'core/login.html', {
        'form': form,
    })


@login_required
def index(request, user=None):
    """oauth callback
    """
    # get user info, set cookie, save user into db

    repos = get_repos()
    # List public and private organizations for the authenticated user.

    content = {'repos': repos}
    return render(request, 'core/index.html', content)


@login_required
@csrf_exempt
def keygen(request):
    """generate SSH key
    """
    SSH_addr = request.POST['addr']
    SSH_user = request.POST['user']
    port = int(request.POST['port'])
    username = request.user.username
    client = pymongo.MongoClient("localhost", 27017)
    db = client[settings.MONGODB_NAME]
    coll = db[settings.MONGODB_SSHKEY]

    spec = {'addr': SSH_addr, 'username': username}
    result = coll.find_one(spec, fields=['sshkey'])
    if not result:
        key_name = base64.b64encode('%s_%s' % (SSH_addr, SSH_user))
        key = ssh_keygen.generate(os.path.join(GERRIT_SSH_KEY_PATH, '%s.id_rsa' % key_name))
        coll.update(spec, {'$set': {'user': SSH_user, 'sshkey': key, 'port': port, 'key_name': key_name}}, True)
    else:
        key = result['sshkey']

    return render(request, 'core/generate.html', {
	'key': key,
    })


@login_required
@csrf_exempt
def test(request):
    """test SSH connection
    """
    SSH_addr = request.POST['addr']
    SSH_user = request.POST['user']
    port = int(request.POST['port'])
    username = request.user.username
    client = pymongo.MongoClient("localhost", 27017)
    db = client[settings.MONGODB_NAME]
    coll = db[settings.MONGODB_SSHKEY]

    spec = {'addr': SSH_addr, 'username': username}
    result = coll.find_one(spec, fields=['sshkey'])
    if not result:
        key_name = base64.b64encode('%s_%s' % (SSH_addr, SSH_user))
        key = ssh_keygen.generate(os.path.join(GERRIT_SSH_KEY_PATH, '%s.id_rsa' % key_name))
        coll.update(spec, {'$set': {'user': SSH_user, 'sshkey': key, 'port': port, 'key_name': key_name}}, True)
    else:
        key = result['sshkey']

    return render(request, 'core/generate.html', {
	'key': key,
    })


@login_required
def keys(request):
    """list all SSH key of user
    """
    username = request.user.username
    client = pymongo.MongoClient("localhost", 27017)
    db = client[settings.MONGODB_NAME]
    coll = db[settings.MONGODB_SSHKEY]

    result = coll.find({'username': username})

    return render(request, 'core/keys.html', {
	'keys': result,
    })


@login_required
def repos(request):
    """List projects visible to caller
    """
    # TODO get user's gerrit info from db, list projects of this gerrit
    username = request.user.username
    SSH_addr = request.GET['addr']
    client = pymongo.MongoClient("localhost", 27017)
    db = client[settings.MONGODB_NAME]
    coll = db[settings.MONGODB_SSHKEY]

    spec = {'addr': SSH_addr, 'username': username}
    result = coll.find_one(spec)
    print result
    repos = gerrit.ls_projects(**result)

    coll = db[settings.MONGODB_GROUPS]
    groups = coll.find({'username': username})

    content = {'repos': repos, 'groups': groups}
    return render(request, 'core/repos.html', content)


@login_required
@csrf_exempt
def groups(request):
    """create a group for saving reposi, return all group.
    """
    username = request.user.username
    client = pymongo.MongoClient("localhost", 27017)
    db = client[settings.MONGODB_NAME]
    coll = db[settings.MONGODB_GROUPS]

    if request.method == "POST":
        name = request.POST.get('name')
        spec = {'name': group, 'username': username}
        coll.update(spec, {'$set': {'name': name}}, True)
    groups = coll.find({'username': username})

    content = {'groups': groups}
    return render(request, 'core/groups.html', content)


@login_required
@csrf_exempt
def group(request, name):
    """list repos of group
    """
    username = request.user.username
    client = pymongo.MongoClient("localhost", 27017)
    db = client[settings.MONGODB_NAME]
    coll = db[settings.MONGODB_REPOS]

    repos = coll.find_one({'group': name, 'username': username}, fields=['repos'])
    return render(request, 'core/group.html', repos)


@login_required
@csrf_exempt
def add_repos(request):
    """add repos to group
    """
    username = request.user.username
    group = request.POST['group']
    repos = request.POST.getlist('repos')
    client = pymongo.MongoClient("localhost", 27017)
    db = client[settings.MONGODB_NAME]
    coll = db[settings.MONGODB_REPOS]

    spec = {'group': group, 'username': username}
    result = coll.find_one(spec, fields=['repos'])
    if result:
        repos.extend(result['repos'])
    repos = list(set(repos))
    coll.update(spec, {'$set': {'repos': repos}}, True)

    content = {'repos': repos}
    return render(request, 'core/group.html', content)


@login_required
@csrf_exempt
def del_repos(request):
    """remove repo from group
    """
    username = request.user.username
    group = request.POST['group']
    repos = request.POST.getlist('repos')
    client = pymongo.MongoClient("localhost", 27017)
    db = client[settings.MONGODB_NAME]
    coll = db[settings.MONGODB_REPOS]

    spec = {'group': group, 'username': username}
    repos = list(set(repos))
    coll.update(spec, {'$set': {'repos': repos}}, True)

    content = {'repos': repos}
    return render(request, 'core/group.html', content)


@login_required
@csrf_exempt
def del_host(request):
    """remove host
    """
    username = request.user.username
    repos = request.GET['host']
    client = pymongo.MongoClient("localhost", 27017)
    db = client[settings.MONGODB_NAME]
    coll = db[settings.MONGODB_REPOS]

    spec = {'group': group, 'username': username}
    repos = list(set(repos))
    coll.update(spec, {'$set': {'repos': repos}}, True)

    content = {'repos': repos}
    return render(request, 'core/group.html', content)


def create_gerrit_stream_event():
    """create gerrit stream event
    """
    p = Process(target=process_event)
    p.start()
    p.join()


def process_event():
    """process gerrit event
    """
    event = gerrit.stream_events()
    if event:
        payload(event)


def payload(data):
    """gerrit payloads
    """
    p = Process(target=process_JJ, args=(data))
    p.start()
    p.join()


def process_JJ(data):
    # FIXME build id is not sync
    print 'Jenkins job' + '-'*80
    J = jenkins.get_server_instance()
    r = J[settings.JENKINS_JOB].invoke(build_params={'data': data})
    start = timezone.now()
    while True:
        status = r.is_queued_or_running()
        print 'is running', status
        build_id = r.get_build_number()
        if not status:
            build_id = r.get_build_number()
            break
    print 'build_id: ', build_id

    branch = data['refUpdate']['refName']
    repo_name = data['refUpdate']['project']
    commit = data['refUpdate']['newRev']
    committer = data['submitter']['username']
    timestamp = timezone.now()

    payload, created = Payload.objects.get_or_create(repo=repo_name, branch=branch)
    payload.committer = committer
    payload.build_id = build_id
    payload.build_job = settings.JENKINS_JOB
    payload.start = start
    payload.end = timezone.now()
    payload.save()

    print '-'*80
    # FIXME GitHub will time out, can we use subprocess to get build status, and set status to badge?
    #while r.get_build().is_running():
    #    print 'job status: ', r.get_build().is_running()
    #    status = r.get_build().get_status()
    Badge.objects.get_or_create(repo=repo_name, branch=branch)

@login_required
def edit_group(request):
    """edit the repos of a repo group
    """
    group_id = request.GET['group']
    repo_list = request.GET['list']

    # TODO fill group, add repos into group
    obj, _ = Repo.objects.get_or_create(repo_id=repo_id)
    obj.repo_list = repo_list
    obj.save()
    return HttpResponseRedirect('/repos/')


@login_required
def create_group(request):
    """create a repos group
    """
    name = request.GET['name']
    host = request.GET['host']

    obj = Repo.objects.get(repo_id=repo_id)

    obj.save()
    return HttpResponseRedirect('/repos/')


@login_required
def repo(request, repo):
    """show last build console and build history
    """
    payloads = Payload.objects.filter(name=repo).order_by('-id')
    current = payloads[0] if payloads else {}
    if current:
        J = jenkins.get_server_instance()
        console = J[current.build_job].get_build(int(current.build_id)).get_console()

    return render(request, 'core/repo.html', locals())


@login_required
def builds(request, repo):
    """show build history
    """
    builds = Payload.objects.filter(name=repo).order_by('-id')
    for build in builds:
        build.message = build.message.strip().splitlines()[0]
    return render(request, 'core/repo.html', locals())


@login_required
def get_build(request, repo, build_id):
    """get specific build information
    """
    J = jenkins.get_server_instance()
    try:
        current = Payload.objects.get(name=repo, build_id=build_id)
    except Payload.DoesNotExist:
        current = {}
    console = J[current.build_job].get_build(int(build_id)).get_console()
    return render(request, 'core/repo.html', locals())
