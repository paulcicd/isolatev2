"""Scoped access-lifecycle API and the management workspace."""
import secrets
import time
from functools import wraps

import isolate_governance as governance
from isolate_governance_ui import render_governance, render_governance_error


def register_governance_api(app, config, runtime_factory, bearer, bounded_json, failure, errors, csrf_token):
    from flask import abort, jsonify, redirect, request, url_for

    def context(mutation=False, form=False):
        token = bearer(allow_browser=True, mutation=mutation and not form)
        runtime = runtime_factory()
        identity = runtime.authenticate(token)
        if identity.get('principal_type') == 'service':
            raise governance.GovernanceError('human_governance_operator_required', 403)
        return runtime.redis, identity

    def guarded(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            try:
                result = function(*args, **kwargs)
                response = app.make_response(result)
                response.headers['Cache-Control'] = 'no-store'
                return response
            except governance.GovernanceError as exc:
                if request.path.startswith('/workspace/governance'):
                    return render_governance_error(config, exc.status), exc.status, {'Cache-Control': 'no-store'}
                return jsonify(error=exc.error), exc.status
            except errors as exc:
                return failure(exc)
        return wrapper

    def payload(fields):
        body = bounded_json(8192)
        if body.get('confirm') is not True or set(body) - set(fields) - {'confirm'}:
            abort(400, description='explicit confirm=true and supported fields are required')
        return {key: value for key, value in body.items() if key != 'confirm'}

    def complete(store, record, status=200):
        # Domain/evidence already committed. A down sink leaves a retryable
        # outbox; never ask clients to repeat the access mutation to republish.
        governance.publish_pending(store, config)
        # Publisher totals include other projects. Expose only this mutation's
        # durable evidence guarantee, never global queue activity to an owner.
        return jsonify(result=record, audit_delivery={'status': 'retained', 'publication': 'retryable_outbox'}), status

    @app.get('/api/v1/governance')
    @guarded
    def governance_dashboard():
        store, identity = context()
        return jsonify(governance.dashboard(store, config, identity, request.args.get('project')))

    @app.post('/api/v1/governance/reviews')
    @guarded
    def governance_review_create():
        store, identity = context(True)
        body = payload(('project', 'reason', 'due_at', 'owner_subject'))
        if not {'project', 'reason'} <= set(body):
            abort(400)
        record = governance.create_review(store, config, identity, idempotency_key=request.headers.get('Idempotency-Key'), **body)
        return complete(store, record, 201)

    @app.post('/api/v1/governance/reviews/<review_id>/decisions')
    @guarded
    def governance_review_decision(review_id):
        store, identity = context(True)
        body = payload(('grant_id', 'decision', 'reason'))
        if set(body) != {'grant_id', 'decision', 'reason'}:
            abort(400)
        return complete(store, governance.decide_review(store, config, identity, review_id, **body))

    @app.post('/api/v1/governance/assignments')
    @guarded
    def governance_assignment_create():
        store, identity = context(True)
        body = payload(('project', 'subject_id', 'username', 'remote_user', 'expires_at', 'starts_at', 'allowed_actions', 'category', 'reason'))
        if not {'project', 'subject_id', 'username', 'remote_user', 'expires_at', 'reason'} <= set(body):
            abort(400)
        return complete(store, governance.create_assignment(store, config, identity,
            idempotency_key=request.headers.get('Idempotency-Key'), **body), 201)

    @app.post('/api/v1/governance/assignments/<assignment_id>/revoke')
    @guarded
    def governance_assignment_revoke(assignment_id):
        store, identity = context(True)
        body = payload(('reason',))
        if set(body) != {'reason'}:
            abort(400)
        return complete(store, governance.revoke_assignment(store, config, identity, assignment_id, body['reason']))

    @app.post('/api/v1/governance/offboarding')
    @guarded
    def governance_offboarding():
        store, identity = context(True)
        body = payload(('subject_id', 'project', 'reason'))
        if set(body) != {'subject_id', 'project', 'reason'}:
            abort(400)
        return complete(store, governance.offboard(store, config, identity, **body))

    @app.get('/workspace/governance')
    @guarded
    def governance_workspace():
        store, identity = context()
        project = request.args.get('project')
        data = governance.dashboard(store, config, identity, project)
        visible_projects = (sorted(set(data['projects']) | set(governance.visible_projects(store, config, identity)))
                            if project else data['projects'])
        return render_governance(config, identity, data, visible_projects, request.args, csrf_token)

    @app.post('/workspace/governance/actions')
    @guarded
    def governance_workspace_action():
        if request.content_length is not None and request.content_length > 8192:
            abort(413)
        supplied = request.form.get('csrf_token', '')
        if not supplied or not secrets.compare_digest(supplied, csrf_token()) or request.form.get('confirm') != 'true':
            abort(403)
        origin = request.headers.get('Origin')
        if origin and origin != str(config.get('dashboard', {}).get('public_url') or '').rstrip('/'):
            abort(403)
        store, identity = context(True, form=True)
        values = request.form
        operation, reason = values.get('operation'), values.get('reason')
        if operation == 'create_review':
            record = governance.create_review(store, config, identity, values.get('project'), reason, idempotency_key=values.get('intent'))
            destination = {'view': 'reviews', 'review': record['id']}
        elif operation == 'review':
            record = governance.decide_review(store, config, identity, values.get('review_id'), values.get('grant_id'), values.get('decision'), reason)
            destination = {'view': 'reviews', 'review': record['id']}
        elif operation == 'assignment':
            try:
                days = int(values.get('expires_days', ''))
            except ValueError:
                abort(400)
            record = governance.create_assignment(store, config, identity, project=values.get('project'), subject_id=values.get('subject_id'), username=values.get('username'),
                remote_user=values.get('remote_user'), expires_at=int(time.time()) + days * 86400, reason=reason,
                allowed_actions=[value.strip() for value in values.get('allowed_actions', '').split(',') if value.strip()], idempotency_key=values.get('intent'))
            destination = {'view': 'assignments', 'assignment': record['id']}
        elif operation == 'revoke_assignment':
            record = governance.revoke_assignment(store, config, identity, values.get('assignment_id'), reason)
            destination = {'view': 'assignments', 'assignment': record['id']}
        elif operation == 'offboard':
            record = governance.offboard(store, config, identity, values.get('subject_id'), values.get('project'), reason)
            destination = {'view': 'offboarding'}
        else:
            abort(400)
        governance.publish_pending(store, config)
        if record['project'] != '*':
            destination['project'] = record['project']
        return redirect(url_for('governance_workspace', **destination), code=303)
