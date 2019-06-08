from flask import Flask, request, render_template,redirect,url_for,jsonify,session
import pymysql.cursors
import hashlib
import os
import time
import datetime
from werkzeug.utils import secure_filename

START_FILE = os.getcwd()+'/static/img/'
EXTENSION_LIST = set(['png', 'jpg', 'jpeg', 'gif'])


app = Flask(__name__)
app.secret_key = 'this_is_supposed_to_be_secret'
app.config['START_FILE'] = START_FILE

conn = pymysql.connect(host='127.0.0.1', user='devapp', database='ios')

def checkUser():
    if 'user' not in session:
        return redirect(url_for('login',error="login required"))

def encrypt(hash_str):
    return hashlib.sha256(hash_str.encode()).hexdigest()

def extension_list(filename):
    return '.' in filename and /filename.rsplit('.', 1)[1].lower() in extension_list

def saveFile(file):
    if file and extension_list(file.filename):
        filename = secure_filename(session['user']+file.filename)
        file.save(os.path.join(app.config['START_FILE'], filename))
        return os.path.join("/static/img", filename)

def getGroups(mail_id):
    cursor = conn.cursor()
    query_string = "SELECT owner_email, foreground_name FROM belong where mail_id=(%s)"
    cursor.execute(query_string,mail_id)
    results_output = cursor.fetchall()
    cursor.close()
    return results_output

@app.route("/", methods = ["GET", "POST"])
def index():
    if 'user' in session:
        cursor = conn.cursor()
        query_string = "SELECT * FROM tag join contentitem ON (contentitem.item_id = tag.item_id) where email_tagged = (%s) and status = 'Pending'"
        cursor.execute(query_string,session['user'])
        store = cursor.fetchall()
        return render_template("index.html", tag_data = store)
    else:
        return render_template("index.html")

#update peding tags that users can accept or deny
@app.route("/tag", methods = ["POST"])
def tag():
    cursor = conn.cursor()
    tag_key = request.form.getlist('store[]')
    status = tag_key[3]
    tagger = tag_key[2]
    taggee = tag_key[1]
    itemid = tag_key[0]
    sql = "UPDATE tag SET status = (%s) WHERE item_id = (%s) AND email_tagger = (%s) AND email_tagged = (%s)"
    print(tagger, taggee, itemid)
    cursor.execute(sql,(status,itemid,tagger, taggee))
    conn.commit()
    cursor.close()
    return render_template("index.html")



@app.route("/login")
def login():
    error = request.args.get('error')
    return render_template("login.html",errors = error )

# Login users
@app.route("/login/user",methods=['GET','POST'])
def loginUser():
    mail_id = request.form["mail_id"]
    password = request.form["password"]
    cursor = conn.cursor()
    sql = "SELECT * FROM Person WHERE mail_id=(%s) AND password=(%s)"
    cursor.execute(sql,(mail_id,encrypt(password)))
    store = cursor.fetchone()
    cursor.close()
    error = None
    if(store):
        session['user'] = mail_id
        return redirect(url_for('post'))
    else:
        message = 'Invalid login or username'
        return redirect(url_for('login', error=message))

@app.route("/signup")
def signup():
    error = request.args.get('error')
    return render_template("signup.html",errors = error)

# Sign up users
@app.route("/signup/user",methods=['GET','POST'])
def signUpUser():
    first_name = request.form["first_name"]
    last_name = request.form["last_name"]
    mail_id = request.form["mail_id"]
    password = request.form["password"]
    secpassword = request.form["2password"]
    result = None
    if password != secpassword:
        message = "Passwords should match"
        return redirect(url_for('signup',error=message))
    if len(mail_id) > 20:
        message = "length cannot exceed 20"
        return redirect(url_for('signup',error=message))
    cursor = conn.cursor()
    try:
        sql = "SELECT * FROM person WHERE mail_id=(%s)"
        cursor.execute(sql,(mail_id))
        result = cursor.fetchone()
    finally:
        if not result:
            password = encrypt(password)
            sql = "INSERT INTO `person` (`mail_id`,`password`,`first_name`,`last_name`) VALUES (%s,%s,%s,%s)"
            cursor.execute(sql,(mail_id,password,first_name,last_name))
            conn.commit()
            cursor.close()
            session['user'] = mail_id
            return redirect(url_for('post'))
        else:
            message = "User Already Exist"
            return redirect(url_for('signup',error=message))

# Render template for post page
@app.route("/post")
def post():
    if 'user' in session:
        session['groups']=getGroups(session['user'])
        return render_template('post.html',mail_id=session['user'],groups=session['groups'])
    else:
        return render_template('post.html',mail_id="Visitor")


def postContent(email_post,post_time,file_path,item_name,is_pub,groups=[]):
    cursor = conn.cursor()
    query_string = 'INSERT INTO `contentitem`(`email_post`,`post_time`,`file_path`,`item_name`,`is_pub`) VALUES(%s,%s,%s,%s,%s)'
    cursor.execute(query_string,(email_post,post_time,file_path,item_name,is_pub))
    conn.commit()
    id = cursor.lastrowid
    query_string = 'SELECT email_post, post_time, item_name, file_path,item_id FROM contentitem WHERE item_id = (%s)'
    cursor.execute(query_string,id)
    store = cursor.fetchone()
    counter = 0
    sharedGroup = []
    for shared in groups:
        if shared == True:
            sharedGroup.append(session['groups'][counter])
            counter+=1
        else:
            counter+=1
    for shared in sharedGroup:
        query_string = 'INSERT INTO `share`(`owner_email`,`foreground_name`,`item_id`) VALUES(%s,%s,%s)'
        cursor.execute(query_string,(shared[0],shared[1],id))
        conn.commit()
    cursor.close()
    return store

# Posting a blog
@app.route("/post/posting/public",methods=['POST'])
def postBlog():
    is_pubB = True
    ts = time.time()
    timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    try:
        upload_file = request.files['file']
        content = request.form["content"]
        file_path = saveFile(upload_file)
        store = postContent(session['user'],timestamp,file_path,content,is_pubB)
        return jsonify({'store':store})
    except:
        content = request.form["content"]
        store = postContent(session['user'], timestamp, 'none', content, is_pubB)
        return jsonify({'store':store})

@app.route("/post/posting/private",methods=['POST'])
def postPrivateBlog():
    content = request.form["content"]
    is_pubB = False
    groups = request.form["group"]
    groups = groups.split(",")
    groups = [True if int(i) == 1 else False for i in groups]
    ts = time.time()
    timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    try:
        upload_file = request.files['file']
        file_path = saveFile(upload_file)
        store = postContent(session['user'],timestamp,file_path,content,is_pubB,groups)
        return jsonify({'store':store})
    except:
        store = postContent(session['user'],timestamp,'none',content,is_pubB,groups)
        return jsonify({'store':store})


# Fetching the viewable blogs
@app.route("/post/blog")
def fetchBlogs():
    if 'user' in session:
        cursor = conn.cursor()
        query_string = 'SELECT DISTINCT * FROM(SELECT email_post, post_time, item_name, file_path, item_id FROM contentitem WHERE is_pub = true AND post_time>=DATE_SUB(NOW(), INTERVAL 1 DAY) UNION all SELECT email_post, post_time, item_name, file_path, item_id FROM belong JOIN share USING(owner_email,fg_name) JOIN contentitem USING(item_id) WHERE email = (%s)) a ORDER BY post_time DESC;'
        cursor.execute(query_string,session['user'])
        store = cursor.fetchall()
        cursor.close()
        return jsonify({'store':store})
    else:
        cursor = conn.cursor()
        query_string = 'SELECT email_post, post_time, item_name, file_path, item_id FROM contentitem WHERE is_pub = true AND post_time>=DATE_SUB(NOW(), INTERVAL 1 DAY) order by post_time DESC'
        cursor.execute(query_string)
        store = cursor.fetchall()
        cursor.close()
        return jsonify({'store':store})

# Fetching detailed info of a specific blog
@app.route("/post/blog/<item_id>")
def detailedBlog(item_id):
    cursor = conn.cursor()
    # we need to check if the current user have access to this page or not.
    query_string = "SELECT is_pub from contentitem where item_id = (%s)"
    cursor.execute(query_string,(item_id))
    result = cursor.fetchone()
    if not result:
        return render_template('content.html',item="You don't have access to this blog",tag='', rate='',file='')
    store = int(result[0])
    if store == 0:
        user = ''
        if 'user' in session:
            query_string = "SELECT foreground_name, owner_email from contentitem JOIN share using (item_id) JOIN belong using(owner_email,foreground_name) where item_id = (%s) and email = (%s)"
            cursor.execute(query_string,(item_id,session['user']))
            user = cursor.fetchone()
        else:
            return redirect(url_for('login',error="It's a private blog, you must login first"))
        if user is None:
            return render_template('content.html',item="False",tag='', rate='',file='')

    # content of a post
    contentItem = 'SELECT * FROM contentitem WHERE item_id = (%s)'
    cursor.execute(contentItem,item_id)
    content = cursor.fetchone()

    # taggee of a post
    tag = 'SELECT first_name,last_name FROM person JOIN Tag ON (Tag.email_tagged = person.email) WHERE Tag.item_id = (%s) AND Tag.status=true'
    cursor.execute(tag,item_id)
    taggee = cursor.fetchall()
    tagger = 'SELECT first_name,last_name FROM person JOIN Tag ON (Tag.email_tagger = person.email) WHERE Tag.item_id = (%s) AND Tag.status=true'
    cursor.execute(tagger,item_id)
    tagger = cursor.fetchall()
    tag = [taggee,tagger]
    result = []
    for t in taggee:
        result.append([t])
    counter = 0
    for t in tagger:
        result[counter].append(t)
        counter += 1



    # rating of a post
    rate = 'SELECT mail_id, rate_time, emoji FROM rate where item_id = (%s)'
    cursor.execute(rate,item_id)
    rating = cursor.fetchall()
    cursor.close()
    return render_template('content.html',item=content,tag=result, rate=rating,file=content[3])


@app.route("/groups")
def GroupManagement():
    if 'user' in session:
        error = request.args.get('error')
        return render_template('GroupManagement.html',errors = error)
    else:
        message = "You need to log in first"
        return redirect(url_for('login',error=message))

@app.route("/groups/fetch")
def groupFetch():
    if 'user' in session:
        cursor = conn.cursor()
        query_string = 'select belong.foreground_name,friendgroup.details,belong.owner_email from belong join friendgroup using(owner_email,foreground_name) where belong.email = (%s)'
        cursor.execute(query_string,session['user'])
        store = cursor.fetchall()
        cursor.close()
        return jsonify({'store':store,'user':session['user']})
    else:
        message = "You need to log in first"
        return redirect(url_for('login',error=message))

@app.route("/groups/create",methods=['GET','POST'])
def createGroup():
    cursor = conn.cursor()
    foreground_name = request.form['groupname']
    details = request.form['details']
    result = None
    try:
        sql = "select * from friendgroup where owner_email = (%s) and foreground_name = (%s)"
        cursor.execute(sql, (session['user'],foreground_name))
        result = cursor.fetchone()
    finally:
        if not result:
            sql = "insert into friendgroup(owner_email, foreground_name, details) Values (%s,%s,%s)"
            cursor.execute(sql, (session['user'], foreground_name, details))
            sql = "insert into belong(mail_id, owner_email, foreground_name) Values (%s,%s,%s)"
            cursor.execute(sql, (session['user'], session['user'], foreground_name))
            conn.commit()
            cursor.close()
            return jsonify({'foreground_name': foreground_name, 'owner':session['user'], 'details': details})
        else:
            message = "Group Already Exist"
            return redirect(url_for('GroupManagement', error=message))
    return jsonify({'name':foreground_name, 'details':details})



@app.route("/groups/friendAdd", methods=['POST'])
def addFriend():
    cursor = conn.cursor()
    first_name = request.form['firstName']
    last_name = request.form['lastName']
    foreground_name = request.form['foreground_name']
    sqlCount = "select count(*) from (select mail_id from person where first_name = (%s) and last_name = (%s)"
    cursor.execute(sqlCount, (first_name,last_name, session['user'], foreground_name))
    count = cursor.fetchone()
    count = count[0]
    print("Count: ", count)

    sqlEmail = "select mail_id from person where first_name = (%s) and last_name = (%s) and mail_id Not In (select mail_id from belong where owner_email = (%s) and fg_name = (%s))"
    cursor.execute(sqlEmail, (first_name, last_name, session['user'], foreground_name))
    token = cursor.fetchall()
    print("FriendID: ", token)

    sqlAlreadyIn = "select * from belong Natural join person where first_name=(%s) and last_name=(%s) and owner_email=(%s) and foreground_name=(%s)"
    cursor.execute(sqlAlreadyIn,(first_name,last_name, session['user'], foreground_name))
    alreadyIn = cursor.fetchall()

    if count > 1:
        return jsonify({"dup": token})

    if count == 1:
        token = token[0]
        sqlInsert = "insert into belong (mail_id, owner_email, foreground_name) values (%s, %s, %s)"
        cursor.execute(sqlInsert, (token, session['user'], foreground_name))
        conn.commit()
        cursor.close()
	print("Error")
        message ="Congratulation! user " + first_name + " " + last_name +" SUCCESSFULLY added!"
        return jsonify({"added":message})

    if alreadyIn:
        message = "user " + first_name + " " + last_name + " is already in this group"
        cursor.close()
	print("Done")
        return jsonify({"alreadyIn": message})

    if count == 0:
        message = "there is no such a user with name " + first_name + " " + last_name
        cursor.close()
        return jsonify({"noUser":message})




@app.route("/groups/friendAddWithEmail", methods = ['POST'])
def addFriendWithEmail():
    cursor = conn.cursor()
    first_name = request.form['firstName']
    last_name = request.form['lastName']
    foreground_name = request.form['foreground_name']
    mail_id = request.form['mail_id']

    sqlCheck = "select mail_id from person where first_name =(%s) and last_name = (%s)"
    cursor.execute(sqlCheck, (first_name, last_name, session['user'], foreground_name))
    available = cursor.fetchall()
    for i in range(len(available)):
        if available[i][0] == mail_id: # a valid input
            sqlInsert = "insert into belong (mail_id, owner_email, foreground_name) values (%s, %s, %s)"
            cursor.execute(sqlInsert, (mail_id, session['user'], foreground_name))
            conn.commit()
            cursor.close()
            message = "Congratulation! user " + first_name + " " + last_name + " SUCCESSFULLY added!"
            return jsonify({"added": message})
    message = "Invalid Email"
    cursor.close()
    return jsonify({"failed":message})

@app.route("/groups/removefriend", methods=['DELETE'])
def removefriend():
    cursor = conn.cursor()
    first_name = request.form['firstName']
    last_name = request.form['lastName']
    foreground_name = request.form['foreground_name']
    sqlCount = "select count(mail_id) from person natural join belong where first_name = (%s) and last_name = (%s) and owner_email = (%s) and foreground_name=(%s) and email not in (%s)"
    cursor.execute(sqlCount, (first_name,last_name, session["user"], foreground_name, session['user']))
    count = cursor.fetchone()
    count = count[0]
    sqlEmail = "select email from person natural join belong where first_name = (%s) and last_name = (%s) and owner_email = (%s) and foreground_name=(%s) and email not in (%s)"
    cursor.execute(sqlEmail, (first_name, last_name, session["user"], foreground_name, session["user"]))
    token = cursor.fetchall()
    if count == 0:
        print("Done")
        cursor.close()
        return jsonify({"noUser":message})
    sqlAlreadyIn = "select first_name, last_name, mail_id from belong Natural join person where first_name=(%s) and last_name=(%s) and owner_email=(%s) and foreground_name=(%s)"
    cursor.execute(sqlAlreadyIn,(first_name,last_name, session['user'], foreground_name))
    alreadyIn = cursor.fetchall()
    if count == 1:
        if token[0][0] == session["user"]:
            cursor.close()
            return
        token = token[0][0]
        deleteNow = "delete from belong where mail_id = (%s) and owner_email = (%s) and foreground_name = (%s)"
        cursor.execute(deleteNow, (token, session['user'], foreground_name))
        conn.commit()
        cursor.close()
        message ="user " + first_name + " " + last_name +" removed"
        return jsonify({"deleted":message})
    else:
        return jsonify({"dup":token})

@app.route("/groups/removefriendwithemail", methods = ['Delete'])
def removefriendwithemail():
    cursor = conn.cursor()
    first_name = request.form['firstName']
    last_name = request.form['lastName']
    foreground_name = request.form['foreground_name']
    mail_id = request.form['mail_id']
    sqlCheck = "select mail_id from person natural join belong where first_name = (%s) and last_name = (%s) and owner_email = (%s) and foreground_name=(%s) and email not in (%s)"
    cursor.execute(sqlCheck, (first_name, last_name, session['user'], foreground_name, session['user']))
    available = cursor.fetchall()
    for i in range(len(available)):
        if available[i][0] == mail_id:
            sqlInsert = "delete FROM belong where mail_id = (%s) and owner_email = (%s)"
            cursor.execute(sqlInsert, (mail_id, session['user'], foreground_name))
            conn.commit()
            cursor.close()
            message = "user " + first_name + " " + last_name + "removed"
            return jsonify({"deleted": message})
    message = "Invalid Email. Be careful PLEASE!"
    cursor.close()
    return jsonify({"failed":message})


@app.route("/post/blog/<item_id>/type",methods=['GET','POST'])
def type(item_id):
    cursor = conn.cursor()
    if request.method == 'POST':
        content = request.form['type']
        query_string = "INSERT into `type`(`mail_id`, `type`, `item_id`) Values (%s,%s,%s)"
        cursor.execute(query_string,(session['user'],content,item_id))
        conn.commit()
        query_string = "SELECT first_name, last_name FROM Person where mail_id=(%s)"
        cursor.execute(query_string,(session['user']))
        name = cursor.fetchone()
        cursor.close()
        return jsonify({'name':name,'type':content})
    elif request.method == 'GET':
        query_string = "SELECT DISTINCT first_name,last_name,type,mail_id FROM type JOIN person USING(mail_id) where item_id=(%s)"
        cursor.execute(query_string,(item_id))
        store = cursor.fetchall()
        cursor.close()
        return jsonify({'store':store})

@app.route("/post/blog/<item_id>/post_tag",methods=['GET','POST'])
def post_tag(item_id):
    cursor = conn.cursor()
    if request.method == 'POST':
        content = request.form['tag']
        taggee = []
        l = []
        members = []

        ts = time.time()
        timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

        for i in range(len(content)):
            if content[i] == '@' and i != 0:
                taggee.append(str(''.join(l)).strip())
                l = []
            elif content[i] == '@' and i == 0:continue
            else:l.append(content[i])
        taggee.append(str(''.join(l)).strip())

        sql1 = "SELECT `mail_id` FROM person WHERE `first_name` = (%s) AND `last_name` = (%s)" 
        sql2 = "INSERT into `tag`(`email_tagged`, `email_tagger`, `item_id`, `status`, `tagtime`) Values (%s, %s, %s, %s, %s)"
        sql3 = "SELECT `email_tagged`, `email_tagger`, `item_id` FROM `tag`"
        status = isAvailable(cursor, item_id)
        if status == 1:
            sql = "SELECT mail_id FROM person"
            cursor.execute(sql)
            members = cursor.fetchall()
        else:
            members = ContentSharedGroup(cursor, item_id)
        message = 'Tagged!'
        dup_name = False
        dup_id = ''
        repeated = False

        for i in taggee:
            space_index = taggee[0].find(' ')
            cursor.execute(sql1, (taggee[0][0 : space_index], taggee[0][space_index+1 : ]))
            taggees_email = cursor.fetchall()
            for j in taggees_email:
                cursor.execute(sql3)
                store = cursor.fetchall()
                newstoredval = (j[0], session['user'], int(item_id))
                repeated = False
                if len(taggees_email) > 1:
                    dup_name = True
                    dup_id = taggees_email
                    message = 'multiple people with same name D:'
                else:
                    for i in store:
                        if ((i[0] == newstoredval[0]) and (i[1] == newstoredval[1]) and (i[2] == newstoredval[2])):
                            repeated = True
                    print(repeated)
                    test = False
                    print(members)
                    for member in members:
                        print(j[0], member, '\n')
                        if member[0] == j[0]:
                            test = True
                    print(test)
                    if repeated == False and test:
                        if j[0] == session['user']:
                            cursor.execute(sql2, (j[0], session['user'], item_id, 1, timestamp))
                            conn.commit()
                        else:
                            cursor.execute(sql2, (j[0], session['user'], item_id, 'Pending', timestamp))
                            conn.commit()
                        message = "Tagged!"
                    else:
                        message = 'Sorry you cannot do this :('
        cursor.close()
        print("message", message)
        return jsonify({"message":message, "repeated": repeated, "dup_name":dup_name, "dup_id":dup_id})

@app.route("/post/blog/<item_id>/tagEmail",methods=['GET','POST'])
def tagEmail(item_id):
    message = 'Tagged!'
    mail_id = request.form['tag']
    cursor = conn.cursor()
    time_calc = time.time()
    timestamp = datetime.datetime.fromtimestamp(time_calc).strftime('%Y-%m-%d %H:%M:%S')
    status = isAvailable(cursor, item_id)
    members = []
    print("status", status)
    if status == 1:
        sql = "SELECT mail_id FROM person"
        cursor.execute(sql)
        members = cursor.fetchall()
    else:
        members = ContentSharedGroup(cursor, item_id)
    sql = "SELECT * FROM `tag` WHERE email_tagged = (%s) AND email_tagger = (%s) AND item_id = (%s)"
    sql2 = "INSERT into `tag`(`email_tagged`, `email_tagger`, `item_id`, `status`, `tagtime`) Values (%s, %s, %s, %s, %s)"
    print("mail_id, members: ", mail_id, members)
    test = False
    for member in members:
        if member[0] == mail_id:
            test = True
    if test:
        cursor.execute(sql, (mail_id, session['user'], item_id))
        dup = cursor.fetchall()
        print(dup)
        int_req = len(dup)
        if int_req == 0:
            cursor.execute(sql2, (mail_id, session['user'], item_id, 'Pending', timestamp))
            conn.commit()
            message = "Tagged"
        else:
            message = 'Error'
    else:
        message = 'Error'
    return message

def isAvailable(cursor, item_id):
    sql_2 = "SELECT is_pub FROM contentitem WHERE itemno = (%s)"
    cursor.execute(sql_2, itemno)
    status = cursor.fetchone()
    return status[0]


def ContentSharedGroup(cursor, item_id):
    sql_1 = "SELECT `foreground_name` FROM share WHERE item_id = (%s)"
    cursor.execute(sql_1, item_id)
    sharedMembers = cursor.fetchall()
    members = MembersCalculate(cursor, sharedGroup) 
    return members

def MembersCalculate(cursor, sharedGroup):
    sql = "SELECT `mail_id` FROM belong WHERE `foreground_name` = (%s)"
    storage = []
    for group in sharedMembers:
        cursor.execute(sql, group[0])
        values = cursor.fetchall();
        for i in values:
            if i[0] not in storage:
                storage.append(i[0])
    return storage

@app.route("/gallery")
def renderGallery():
    return render_template("gallery.html")

@app.route("/post/gallery")
def gallery():
    pointer = conn.cursor()
    if 'user' in session:
        query_string = "SELECT DISTINCT file_path FROM contentItem JOIN share USING(item_id) JOIN belong ON(belong.owner_email = share.owner_email AND belong.fg_name = share.fg_name) WHERE belong.mail_id = (%s) UNION all SELECT DISTINCT file_path FROM contentItem where is_pub = true"
        pointer.execute(query_string,session['user'])
    else:
        query_string = "SELECT file_path FROM contentItem where is_pub = true"
        pointer.execute(query_string)
    results = pointer.fetchall()
    return jsonify({'results':results})


@app.route("/logout")
def logout():
    return redirect(url_for('index'))

if __name__ == "__main__":
	app.run(host='0.0.0.0',debug=True)
