from flask import (flash, jsonify, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.sql.expression import desc
from werkzeug.utils import secure_filename

from learn_net import app, bcrypt, db, s3, session
from learn_net.helpers import (rename_kit_file, save_kit_file,
                               save_profile_picture, sslify,
                               generate_youtube_embed_url, get_video_id)
from learn_net.models import Kit, KitFile, KitTag, User, YoutubeVideoId

from learn_net.forms import (SignInForm, SignUpForm, UpdateAccountForm,
                             CreateKitForm, EditKitForm, UploadKitFilesForm,
                             ExtendedSearchForm, AddYoutubeVideoForm)


@app.route('/')
@sslify
def index():
    return render_template('index.html')


@app.route('/signup', methods=['GET', 'POST'])
@sslify
def signup():
    # create a new user, then sign them in

    signUpForm = SignUpForm()
    if signUpForm.validate_on_submit():

        user = User(
            username=signUpForm.username.data,
            email=signUpForm.email.data,
            password=bcrypt.generate_password_hash(
                signUpForm.password.data).decode('utf-8')
        )

        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash('Account created!', 'success')

        return redirect(url_for('index'))
    return render_template('signup.html', signUpForm=signUpForm)


@app.route("/signin", methods=['GET', 'POST'])
@sslify
def signin():
    # sign in user

    signInForm = SignInForm()
    if signInForm.validate_on_submit():
        user = User.query.filter_by(email=signInForm.email.data).first()

        if bcrypt.check_password_hash(user.password, signInForm.password.data):
            login_user(user, remember=signInForm.remember.data)

            next_page = request.args.get('next')
            flash('Successfully signed in!', 'success')

            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            flash('Error signing in. Check your password.', 'danger')
    return render_template('signin.html', signInForm=signInForm)


@app.route('/signout')
@sslify
@login_required
def signout():
    # sign out user

    logout_user()
    flash('You are logged out.', 'danger')

    return redirect(url_for('index'))


@app.route('/<string:username>', methods=['GET', 'POST'])
@sslify
def account(username):
    # view account information

    user = User.query.filter_by(username=username).first()

    if not user:
        flash('That page does not exist.', 'danger')
        return redirect(url_for('index'))

    return render_template('account.html', user=user)


@app.route('/<string:username>/edit', methods=['GET', 'POST'])
@sslify
@login_required
def edit_account(username):
    user = User.query.filter_by(username=username).first()

    if not user:
        flash('That page does not exist.')
        if request.referrer:
            return redirect(request.referrer)
        return redirect(url_for('index'))

    if not user.id == current_user.id:
        flash('You\'re not allowed to do that.', 'danger')
        if request.referrer:
            return redirect(request.referrer)
        return redirect(url_for('index'))

    updateAccountForm = UpdateAccountForm()

    if updateAccountForm.validate_on_submit():
        changed = False
        if current_user.username != updateAccountForm.username.data:
            current_user.username = updateAccountForm.username.data
            changed = True

        if current_user.email != updateAccountForm.email.data:
            current_user.email = updateAccountForm.email.data
            changed = True

        if updateAccountForm.pfp_file.data:
            save_profile_picture(updateAccountForm.pfp_file.data)
            changed = True

        db.session.commit()

        if changed:
            flash('Your account has been updated.', 'info')

            # do this to update the route
            return redirect(url_for('account', username=user.username))

    elif request.method == 'GET':
        # pre-fill fields
        updateAccountForm.username.data = current_user.username
        updateAccountForm.email.data = current_user.email

    return render_template('edit_account.html',
                           updateAccountForm=updateAccountForm)


@app.route('/browse', methods=['GET'])
@sslify
def browse():
    # browse index
    # TODO browse route

    extendedSearchForm = ExtendedSearchForm(request.args, meta={
        'csrf': False
    })

    query = request.args.get('query')

    if query != '' and query is not None:

        page = request.args.get('page', 1, type=int)

        # join with kit file,
        # to filter out kits that don't yet have files in them
        result_kits = Kit.query.filter(
            Kit.title.like(f'%{query}%')).filter(Kit.files.any())

        if extendedSearchForm.validate():
            from_user = request.args.get('from_user')
            from_category = request.args.get('from_category')
            sort_by = request.args.get('sort_by')

            if current_user.is_authenticated:
                result_kits = result_kits.\
                    filter(Kit.owner.has(User.id != current_user.id))

            if from_user != '' and from_user is not None:
                result_kits = result_kits.\
                    filter(Kit.owner.has(User.username.like(f'%{from_user}%')))

            if from_category != 'Any category' and from_category is not None:
                result_kits = result_kits.filter(Kit.category == from_category)

            if sort_by == 'Recency' and sort_by is not None:
                result_kits = result_kits\
                    .order_by(desc(KitFile.date_uploaded))

            show_bad_search_image = result_kits.count() == 0

        result_kits = result_kits.paginate(
            page=page, per_page=10, error_out=False)

        return render_template('browse.html',
                               extendedSearchForm=extendedSearchForm,
                               result_kits=result_kits,
                               show_bad_search_image=show_bad_search_image)

    # if user is just requesting the page, return an empty list for the results
    return render_template('browse.html',
                           extendedSearchForm=extendedSearchForm,
                           result_kits=[],
                           show_bad_search_image=False)


@app.route('/kits')
@sslify
@login_required
def kits():
    # view user's kits, saved kits, favourited kits, etc.

    userKits = Kit.query.filter_by(user_id=current_user.id)

    return render_template('kits.html', userKits=userKits)


@app.route('/kits/create', methods=['GET', 'POST'])
@sslify
@login_required
def create_kit():
    # allow users to create kit

    createKitForm = CreateKitForm()

    if createKitForm.validate_on_submit():
        kit = Kit(
            owner=current_user,
            title=createKitForm.title.data,
            kit_description=createKitForm.kit_description.data,
            category=createKitForm.category.data
        )
        db.session.add(kit)
        db.session.flush()
        # flush so that kit.id is generated without having to commit first

        for tag in createKitForm.tags.data.split(','):
            kitTag = KitTag(tag=tag, kit_id=kit.id)
            db.session.add(kitTag)

        db.session.commit()

        flash('Successfully created kit!', 'success')
        return redirect(url_for('kits'))

    return render_template('create_kit.html', createKitForm=createKitForm)


@app.route('/kits/<int:kitID>', methods=['GET', 'POST'])
@sslify
def view_kit(kitID):
    # view kit information

    kit = Kit.query.filter_by(id=kitID).first()

    if not kit:
        flash('That page does not exist.', 'danger')
        return redirect(url_for('index'))

    uploadKitFilesForm = UploadKitFilesForm()

    addYoutubeVideoForm = AddYoutubeVideoForm()

    if uploadKitFilesForm.validate_on_submit():
        # check that the files the user uploaded
        # doesn't exceed maximum number of files allowed
        total_file_count = len(kit.files) + len(uploadKitFilesForm.files.data)
        if total_file_count > app.config['MAX_KIT_FILE_COUNT']:
            flash('A kit can only have a maximum of 10 files.', 'warning')
            return redirect(url_for('kits'))

        for f in uploadKitFilesForm.files.data:
            filename = secure_filename(f.filename)
            if any(filename == file.filename for file in kit.files):
                flash(
                    'That file already exists in this kit. If it doesn\'t, check the filename.', 'danger')
                return redirect(url_for('view_kit', kitID=kitID))

            file = KitFile(filename=save_kit_file(kit.id, f), kit_id=kit.id)
            db.session.add(file)

        db.session.commit()

        flash('Your changes have been saved.', 'success')

    if addYoutubeVideoForm.validate_on_submit():
        video_url = addYoutubeVideoForm.video_url.data

        video_id = get_video_id(video_url)
        video_id = YoutubeVideoId(kit_id=kit.id, video_id=video_id)

        db.session.add(video_id)
        db.session.commit()

        flash('Video added.', 'success')

    for file in kit.files:
        file.key = '/'.join(['user_kits', str(kit.id), file.filename])

    EMBED_RESOLUTION = (720, 480)
    embed_urls = (
        generate_youtube_embed_url(video_id.video_id)
        for video_id in kit.youtube_video_ids
    )

    return render_template('view_kit.html',
                           kit=kit,
                           uploadKitFilesForm=uploadKitFilesForm,
                           addYoutubeVideoForm=addYoutubeVideoForm,
                           files=kit.files,
                           embed_urls=embed_urls,
                           height=EMBED_RESOLUTION[0],
                           width=EMBED_RESOLUTION[1])


@app.route('/kits/<int:kitID>/edit', methods=['GET', 'POST'])
@sslify
@login_required
def edit_kit(kitID):
    kit = Kit.query.filter_by(id=kitID).first()
    if kit.owner.id != current_user.id:
        flash('You\'re not allowed to do that.', 'danger')
        return redirect(request.referrer)

    editKitForm = EditKitForm(kit)
    if editKitForm.validate_on_submit():
        changed = False

        if editKitForm.title.data:
            kit.title = editKitForm.title.data
            changed = True

        if editKitForm.kit_description.data:
            kit.kit_description = editKitForm.kit_description.data
            changed = True

        if editKitForm.category.data:
            kit.category = editKitForm.category.data
            changed = True

        if editKitForm.tags.data:
            for tag in kit.tags:
                db.session.delete(tag)
            for tag in editKitForm.tags.data.split(','):
                new_tag = KitTag(tag=tag, kit_id=kit.id)
                db.session.add(new_tag)
            changed = True

        for file in kit.files:
            if file.filename != editKitForm[f'{file.filename}-filename'].data:
                file.filename = rename_kit_file(
                    kitID,
                    file.filename,
                    editKitForm[f'{file.filename}-filename'].data)

        db.session.commit()

        if changed:
            flash('Changes saved.', 'success')
            return redirect(url_for('edit_kit', kitID=kitID))

    elif request.method == 'GET':
        editKitForm.title.data = kit.title
        editKitForm.kit_description.data = kit.kit_description
        editKitForm.category.data = kit.category
        editKitForm.tags.data = ','.join([tag.tag for tag in kit.tags])

        for file in kit.files:
            editKitForm[f'{file.filename}-filename'].data = file.filename

    return render_template('edit_kit.html', editKitForm=editKitForm, kit=kit)


@app.route('/kits/<int:kitID>/delete', methods=['POST'])
@sslify
@login_required
def delete_kit(kitID):
    kit = Kit.query.filter_by(id=kitID).first()

    if current_user.id != kit.owner.id:
        flash('You\'re not allowed to do that.')
        if request.referrer:
            return redirect(request.referrer)
        return redirect(url_for('kits'))

    if not kit:
        return redirect(url_for('index'))

    for tag in kit.tags:
        db.session.delete(tag)

    db.session.delete(kit)
    db.session.commit()

    s3.Bucket(app.config['AWS_S3_BUCKET_NAME']).delete_objects(
        Delete={
            'Objects': [
                {
                    'Key': '/'.join(['user_kits', str(kitID)])
                }
            ] + [
                {
                    'Key': '/'.join(['user_kits', str(kitID), file.filename])
                }
                for file in kit.files
            ]
        }
    )

    flash('Kit deleted successfully', 'success')
    if request.referrer:
        return redirect(request.referrer)
    return redirect(url_for('kits'))


@app.route('/kits/<int:kitID>/delete/<path:filename>')
@sslify
@login_required
def delete_kit_file(kitID, filename):
    kit = Kit.query.filter_by(id=kitID).first()
    if not kit:
        flash('That page does not exist.', 'danger')
        return redirect(url_for('kits'))

    if filename not in [file.filename for file in kit.files]:
        flash('That page does not exist.', 'danger')
        return redirect(url_for('kits'))

    if current_user.id != kit.owner.id:
        flash('You aren\'t allowed to do that.', 'danger')
        return redirect(url_for('kits'))

    for file in kit.files:
        if file.filename == filename:
            db.session.delete(file)
            break

    db.session.commit()

    s3.Bucket(app.config['AWS_S3_BUCKET_NAME']).delete_objects(
        Delete={
            'Objects': [
                {
                    'Key': '/'.join(['user_kits', str(kitID), filename])
                }
            ]
        }
    )

    flash('File deleted.', 'warning')

    return redirect(url_for('edit_kit', kitID=kitID))


@app.route('/getusername')
@sslify
def getusername():
    email = request.args.get('email')
    user = User.query.filter_by(email=email).first()
    result = user.username if user else None
    return jsonify({"username": result})
