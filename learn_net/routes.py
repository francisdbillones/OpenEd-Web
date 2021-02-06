from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from learn_net.forms import *
from learn_net.models import ContentTag, User, Content
from learn_net import app, db, bcrypt, session

from learn_net.helpers import save_profile_picture, delete_profile_picture, save_content_file, getFileType

import secrets


@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    # create a new user and sign in
    
    form = SignUpForm()
    if form.validate_on_submit():
        
        user = User(
            username=form.username.data,
            email=form.email.data,
            password=bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        )

        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        flash('Account created!', 'success')
        
        return redirect(url_for('index'))
    return render_template('signup.html', form=form)
    
@app.route("/signin", methods=['GET', 'POST'])
def signin():
    # sign in user
    
    form = SignInForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        
        if bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            
            next_page = request.args.get('next')
            flash('Successfully signed in!', 'success')
            return redirect(url_for('index')) if not next_page else redirect(next_page)
        else:
            flash('Error signing in. Check your password.', 'danger')
    return render_template('signin.html', form=form)

@app.route('/signout')
@login_required
def signout():
    # sign out user
    
    session.clear()
    logout_user()
    flash('You are logged out.', 'danger')
    
    return redirect(url_for('index'))

@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    form = UpdateAccountForm()
    
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        
        if form.pfp_file.data:
            delete_profile_picture(current_user.pfp_file)
            current_user.pfp_file = save_profile_picture(form.pfp_file.data)
        
        db.session.commit()
        flash('Your account has been updated!', 'success')
        return redirect(url_for('account'))
    
    elif request.method == 'GET':
        # pre-fill fields
        form.username.data = current_user.username
        form.email.data = current_user.email
        
    profile_image = url_for('static', filename=f'images/{ current_user.pfp_file }')
    return render_template('account.html', profile_image=profile_image, form=form)

@app.route('/browse', methods=['GET', 'POST'])
def browse():
    # browse index
    # TODO browse route
    
    flash('That page does not exist yet, sorry.', 'info')
    return redirect(url_for('index'))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    # upload new content
    # TODO upload route
    
    form = UploadContentForm()
    
    if form.validate_on_submit():
        content = Content(
            author = current_user,
            title = form.title.data,
            school = form.school.data,
            content_file = save_content_file(form.file.data),
            file_type = getFileType(form.file.data)
        )
        db.session.add(content)
        db.session.flush()

        tags = [tag.strip() for tag in form.tags.data.split()]
        for tag in tags:
            contentTag = ContentTag(tag=tag, content_id=content.id)
            db.session.add(contentTag)
        
        db.session.commit()
        
        flash('Uploaded!', 'success')
        return redirect(url_for('index'))
    return render_template('upload.html', form=form)

@app.route('/getusername')
def getusername():
    email = request.args.get('email')
    user = User.query.filter_by(email=email).first()
    result = user.username if user else None
    return jsonify({"username": result})

if __name__ == '__main__':
    app.run(debug=True)