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
        return redirect(url_for('login',error="login first"))

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
    query_string = "SELECT owner_email, fg_name FROM belong where mail_id=(%s)"
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
        data = cursor.fetchall()
        return render_template("index.html", tag_data = data)
    else:
        return render_template("index.html")

#update peding tags that users can accept or deny
@app.route("/tag", methods = ["POST"])
def tag():
    cursor = conn.cursor()
    tag_key = request.form.getlist('data[]')
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
    pwd = request.form["pwd"]
    cursor = conn.cursor()
    sql = "SELECT * FROM Person WHERE mail_id=(%s) AND password=(%s)"
    cursor.execute(sql,(mail_id,encrypt(pwd)))
    data = cursor.fetchone()
    cursor.close()
    error = None
    if(data):
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
    fname = request.form["fname"]
    lname = request.form["lname"]
    mail_id = request.form["mail_id"]
    pwd = request.form["pwd"]
    secPwd = request.form["2pwd"]
    result = None
    if pwd != secPwd:
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
            pwd = encrypt(pwd)
            sql = "INSERT INTO `person` (`mail_id`,`password`,`fname`,`lname`) VALUES (%s,%s,%s,%s)"
            cursor.execute(sql,(mail_id,pwd,fname,lname))
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
    data = cursor.fetchone()
    counter = 0
    sharedGroup = []
    for shared in groups:
        if shared == True:
            sharedGroup.append(session['groups'][counter])
            counter+=1
        else:
            counter+=1
    for shared in sharedGroup:
        query_string = 'INSERT INTO `share`(`owner_email`,`fg_name`,`item_id`) VALUES(%s,%s,%s)'
        cursor.execute(query_string,(shared[0],shared[1],id))
        conn.commit()
    cursor.close()
    return data

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
        data = postContent(session['user'],timestamp,file_path,content,is_pubB)
        return jsonify({'data':data})
    except:
        content = request.form["content"]
        data = postContent(session['user'], timestamp, 'none', content, is_pubB)
        return jsonify({'data':data})

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
        data = postContent(session['user'],timestamp,file_path,content,is_pubB,groups)
        return jsonify({'data':data})
    except:
        data = postContent(session['user'],timestamp,'none',content,is_pubB,groups)
        return jsonify({'data':data})


# Fetching the viewable blogs
@app.route("/post/blog")
def fetchBlogs():
    if 'user' in session:
        cursor = conn.cursor()
        query_string = 'SELECT DISTINCT * FROM(SELECT email_post, post_time, item_name, file_path, item_id FROM contentitem WHERE is_pub = true AND post_time>=DATE_SUB(NOW(), INTERVAL 1 DAY) UNION all SELECT email_post, post_time, item_name, file_path, item_id FROM belong JOIN share USING(owner_email,fg_name) JOIN contentitem USING(item_id) WHERE email = (%s)) a ORDER BY post_time DESC;'
        cursor.execute(query_string,session['user'])
        data = cursor.fetchall()
        cursor.close()
        return jsonify({'data':data})
    else:
        cursor = conn.cursor()
        query_string = 'SELECT email_post, post_time, item_name, file_path, item_id FROM contentitem WHERE is_pub = true AND post_time>=DATE_SUB(NOW(), INTERVAL 1 DAY) order by post_time DESC'
        cursor.execute(query_string)
        data = cursor.fetchall()
        cursor.close()
        return jsonify({'data':data})

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
    data = int(result[0])
    if data == 0:
        user = ''
        if 'user' in session:
            query_string = "SELECT fg_name, owner_email from contentitem JOIN share using (item_id) JOIN belong using(owner_email,fg_name) where item_id = (%s) and email = (%s)"
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
    tag = 'SELECT fname,lname FROM person JOIN Tag ON (Tag.email_tagged = person.email) WHERE Tag.item_id = (%s) AND Tag.status=true'
    cursor.execute(tag,item_id)
    taggee = cursor.fetchall()
    tagger = 'SELECT fname,lname FROM person JOIN Tag ON (Tag.email_tagger = person.email) WHERE Tag.item_id = (%s) AND Tag.status=true'
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
    print('fetching');
    if 'user' in session:
        cursor = conn.cursor()
        query_string = 'select belong.fg_name,friendgroup.description,belong.owner_email from belong join friendgroup using(owner_email,fg_name) where belong.email = (%s)'
        cursor.execute(query_string,session['user'])
        data = cursor.fetchall()
        cursor.close()
        return jsonify({'data':data,'user':session['user']})
    else:
        message = "You need to log in first"
        return redirect(url_for('login',error=message))

@app.route("/groups/create",methods=['GET','POST'])
def createGroup():
    cursor = conn.cursor()
    fg_name = request.form['groupname']
    description = request.form['description']
    result = None
    try:
        sql = "select * from friendgroup where owner_email = (%s) and fg_name = (%s)"
        cursor.execute(sql, (session['user'],fg_name))
        result = cursor.fetchone()
    finally:
        if not result:
            sql = "insert into friendgroup(owner_email, fg_name, description) Values (%s,%s,%s)"
            cursor.execute(sql, (session['user'], fg_name, description))
            sql = "insert into belong(mail_id, owner_email, fg_name) Values (%s,%s,%s)"
            cursor.execute(sql, (session['user'], session['user'], fg_name))
            conn.commit()
            cursor.close()
            return jsonify({'fg_name': fg_name, 'owner':session['user'], 'description': description})
        else:
            message = "Group Already Exist"
            return redirect(url_for('GroupManagement', error=message))
    # Return statement is for updating UI using AJAX
    return jsonify({'name':fg_name, 'description':description})
            #return redirect(url_for('GroupManagement',error=message))



@app.route("/groups/friendAdd", methods=['POST'])
def addFriend():
    cursor = conn.cursor()
    fName = request.form['firstName']
    lName = request.form['lastName']
    fg_name = request.form['fg_name']
    print("in addFriend")

    '''# of people with such name not in group'''
    sqlCount = "select count(*) from (select mail_id from person where fname = (%s) and lname = (%s)"
    cursor.execute(sqlCount, (fName,lName, session['user'], fg_name))
    count = cursor.fetchone()
    count = count[0] # reformat count
    print("Count: ", count)

    sqlEmail = "select mail_id from person where fname = (%s) and lname = (%s) and mail_id Not In (select mail_id from belong where owner_email = (%s) and fg_name = (%s))"
    cursor.execute(sqlEmail, (fName, lName, session['user'], fg_name))
    friendID = cursor.fetchall()
    print("FriendID: ", friendID)

    sqlAlreadyIn = "select * from belong Natural join person where fname=(%s) and lname=(%s) and owner_email=(%s) and fg_name=(%s)"
    cursor.execute(sqlAlreadyIn,(fName,lName, session['user'], fg_name))
    alreadyIn = cursor.fetchall()

    if count > 1:
        return jsonify({"dup": friendID})

    if count == 1:
        print("not in")
        friendID = friendID[0]
        sqlInsert = "insert into belong (mail_id, owner_email, fg_name) values (%s, %s, %s)"
        cursor.execute(sqlInsert, (friendID, session['user'], fg_name))
        conn.commit()
        cursor.close()
        message ="Congratulation! user " + fName + " " + lName +" SUCCESSFULLY added!"
        return jsonify({"added":message})

    if alreadyIn:
        message = "user " + fName + " " + lName + " is already in this group"
        print("AlreadyIn")
        cursor.close()
        return jsonify({"alreadyIn": message})

    if count == 0:
        message = "there is no such a user with name " + fName + " " + lName
        cursor.close()
        return jsonify({"noUser":message})




@app.route("/groups/friendAddWithEmail", methods = ['POST'])
def addFriendWithEmail():
    print("in addFriendWithEmail")
    cursor = conn.cursor()
    fName = request.form['firstName']
    lName = request.form['lastName']
    fg_name = request.form['fg_name']
    mail_id = request.form['mail_id']
    print(fName, lName)

    sqlCheck = "select mail_id from person where fname =(%s) and lname = (%s)"
    cursor.execute(sqlCheck, (fName, lName, session['user'], fg_name))
    available = cursor.fetchall()
    for i in range(len(available)):
        if available[i][0] == mail_id: # a valid input
            sqlInsert = "insert into belong (mail_id, owner_email, fg_name) values (%s, %s, %s)"
            cursor.execute(sqlInsert, (mail_id, session['user'], fg_name))
            conn.commit()
            cursor.close()
            message = "Congratulation! user " + fName + " " + lName + " SUCCESSFULLY added!"
            return jsonify({"added": message})
    message = "Invalid Email. Be careful PLEASE!"
    cursor.close()
    return jsonify({"failed":message})

@app.route("/groups/defriend", methods=['DELETE'])
def deFriend():
    cursor = conn.cursor()
    fName = request.form['firstName']
    lName = request.form['lastName']
    fg_name = request.form['fg_name']
    
    sqlCount = "select count(mail_id) from person natural join belong where fname = (%s) and lname = (%s) and owner_email = (%s) and fg_name=(%s) and email not in (%s)"
    cursor.execute(sqlCount, (fName,lName, session["user"], fg_name, session['user']))
    count = cursor.fetchone()
    count = count[0] # reformat count
    print("count: ",count)
    sqlEmail = "select email from person natural join belong where fname = (%s) and lname = (%s) and owner_email = (%s) and fg_name=(%s) and email not in (%s)"
    cursor.execute(sqlEmail, (fName, lName, session["user"], fg_name, session["user"]))
    friendID = cursor.fetchall()
    print("FINAL STEP??? of course not")
    if count == 0:
        print("0")
        message = "there is no such a user with name " + fName + " " + lName + " in this group. btw, you can't delete youself"
        cursor.close()
        return jsonify({"noUser":message})
    sqlAlreadyIn = "select fname, lname, mail_id from belong Natural join person where fname=(%s) and lname=(%s) and owner_email=(%s) and fg_name=(%s)"
    cursor.execute(sqlAlreadyIn,(fName,lName, session['user'], fg_name))
    alreadyIn = cursor.fetchall()
    if count == 1:
        print("1")
        print("User is In")
        if friendID[0][0] == session["user"]:
            print("suicide")
            message = "You can't do that! You are the Master of this group!"
            cursor.close()
            return jsonify({"suicide":message})
        friendID = friendID[0][0]
        sqlDelete = "delete from belong where mail_id = (%s) and owner_email = (%s) and fg_name = (%s)"
        cursor.execute(sqlDelete, (friendID, session['user'], fg_name))
        conn.commit()
        cursor.close()
        message ="All Right! user " + fName + " " + lName +" SADLY deleted!"
        return jsonify({"deleted":message})
    else:
        return jsonify({"dup":friendID})

@app.route("/groups/friendDeleteWithEmail", methods = ['Delete'])
def deFriendWithEmail():
    print("in Delete FriendWithEmail")
    cursor = conn.cursor()
    fName = request.form['firstName']
    lName = request.form['lastName']
    fg_name = request.form['fg_name']
    mail_id = request.form['mail_id']
    print(fName, lName)
    sqlCheck = "select mail_id from person natural join belong where fname = (%s) and lname = (%s) and owner_email = (%s) and fg_name=(%s) and email not in (%s)"
    cursor.execute(sqlCheck, (fName, lName, session['user'], fg_name, session['user']))
    available = cursor.fetchall()
    print("Given: ", mail_id)
    for i in range(len(available)):
        print("checking ", available[i][0])
        if available[i][0] == mail_id:
            sqlInsert = "delete from belong where mail_id = (%s) and owner_email = (%s) and fg_name = (%s)"
            cursor.execute(sqlInsert, (mail_id, session['user'], fg_name))
            conn.commit()
            cursor.close()
            message = "All Right! user " + fName + " " + lName +" SADLY deleted!"
            return jsonify({"deleted": message})
    message = "Invalid Email. Be careful PLEASE!"
    cursor.close()
    return jsonify({"failed":message})


@app.route("/post/blog/<item_id>/comment",methods=['GET','POST'])
def comment(item_id):
    cursor = conn.cursor()
    if request.method == 'POST':
        content = request.form['comment']
        query_string = "INSERT into `comment`(`mail_id`, `comment`, `item_id`) Values (%s,%s,%s)"
        cursor.execute(query_string,(session['user'],content,item_id))
        conn.commit()
        query_string = "SELECT fname, lname FROM Person where mail_id=(%s)"
        cursor.execute(query_string,(session['user']))
        name = cursor.fetchone()
        cursor.close()
        return jsonify({'name':name,'comment':content})
    elif request.method == 'GET':
        print("hahah")
        query_string = "SELECT DISTINCT fname,lname,comment,mail_id FROM comment JOIN person USING(mail_id) where item_id=(%s)"
        cursor.execute(query_string,(item_id))
        data = cursor.fetchall()
        cursor.close()
        return jsonify({'data':data})

@app.route("/post/blog/<item_id>/tag",methods=['GET','POST'])
def posttag(item_id):
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

        sql1 = "SELECT `mail_id` FROM person WHERE `fname` = (%s) AND `lname` = (%s)" 
        sql2 = "INSERT into `tag`(`email_tagged`, `email_tagger`, `item_id`, `status`, `tagtime`) Values (%s, %s, %s, %s, %s)"
        sql3 = "SELECT `email_tagged`, `email_tagger`, `item_id` FROM `tag`"
        status = isAvailable(cursor, item_id)
        print("status", status)
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
            #print('user: '+ session['user'])
            space_index = taggee[0].find(' ')
            #print(taggee[0][0 : space_index], taggee[0][space_index+1 : ])
            cursor.execute(sql1, (taggee[0][0 : space_index], taggee[0][space_index+1 : ]))
            taggees_email = cursor.fetchall()
            #print(taggees_email)
            for j in taggees_email:
                cursor.execute(sql3)
                data = cursor.fetchall()
                print("dup data", data)
                newData = (j[0], session['user'], int(item_id))
                print(type(newData))
                repeated = False
                if len(taggees_email) > 1:
                    dup_name = True
                    dup_id = taggees_email
                    message = 'multiple people with same name D:'
                else:
                    for i in data:
                        if ((i[0] == newData[0]) and (i[1] == newData[1]) and (i[2] == newData[2])):
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
                            print('WHYYYYYYYYYY')
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
    ts = time.time()
    timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
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
    print("message2", message)
    return message

def isAvailable(cursor, item_id):
    sql_2 = "SELECT is_pub FROM contentitem WHERE itemno = (%s)"
    cursor.execute(sql_2, itemno)
    status = cursor.fetchone()
    return status[0]


def ContentSharedGroup(cursor, item_id):
    sql_1 = "SELECT `fg_name` FROM share WHERE item_id = (%s)"
    cursor.execute(sql_1, item_id)
    sharedMembers = cursor.fetchall()
    members = MembersCalculate(cursor, sharedGroup) 
    return members

def MembersCalculate(cursor, sharedGroup):
    sql = "SELECT `mail_id` FROM belong WHERE `fg_name` = (%s)"
    storage = []
    for group in sharedMembers:
        cursor.execute(sql, group[0])
        values = cursor.fetchall();
        for i in values:
            if i[0] not in storage:
                storage.append(i[0])
    print('storage', storage)
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
    session.clear()
    return redirect(url_for('index'))

if __name__ == "__main__":
	app.run(host='0.0.0.0',debug=True)
