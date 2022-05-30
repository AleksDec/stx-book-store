from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
import requests
import os
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
# --- Creating database ---
# --- Changing the database name on DATABASE_URL for the deployment ---
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL_POSTGRESQL")
# --- Optional silencing the deprecation warning in the console ---
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
# --- Initializing Marshmallow ---
ma = Marshmallow(app)

# --- Enabling SQLAlchemy connection to a database by creating a model ---
class Books(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(200), unique=True, nullable=True)
    title = db.Column(db.String(200), unique=False, nullable=False)
    authors = db.Column(db.String, unique=False, nullable=False)
    acquired = db.Column(db.Boolean, unique=False, nullable=False)
    published_year = db.Column(db.String(20), unique=False, nullable=False)
    thumbnail = db.Column(db.Text, unique=False, nullable=True)

    def __init__(self, external_id, title, authors, acquired, published_year, thumbnail):
        self.external_id = external_id
        self.title = title
        self.authors = authors
        self.acquired = acquired
        self.published_year = published_year
        self.thumbnail = thumbnail

db.create_all()


# ------ Generating marshmallow Schema from model using SQLAlchemySchema ------
class BookSchema(ma.Schema):
    class Meta:
        fields = ("id", "external_id", "title", "authors", "acquired", "published_year", "thumbnail")
# ------ Initializing Schema ------
book_schema = BookSchema()
books_schema = BookSchema(many=True)


# ------ Dumping all Books and listing ids ------
all_books = Books.query.all()
all_books_dumped = books_schema.dump(all_books)
all_books_ids = [record['id'] for record in books_schema.dump(all_books)]


# ------ Home ------
@app.route("/")
def home():
    return '<h1>STX BookStore</h1>'


# ------ Api Specification ------
@app.route("/api_spec")
def api_spec():
    return jsonify(info={"version": "2022.05.16"})


# ------ Getting the list of books, filtering the results by title, author, publication year or the acquired state ------
filter_options_names = ["title", "authors", "acquired", "from", "to"]

def filters():

    intersection_ids = all_books_ids

    for arg in request.args:
        filtered_ids = []
        if arg not in filter_options_names[3:]:
            for record in all_books_dumped:
                if request.args.get(arg) in str(record[arg]).lower():
                    filtered_ids.append(record['id'])
        else:
            if arg == "from":
                for record in all_books_dumped:
                    if int(record["published_year"].split("-")[0]) >= int(request.args.get("from")):
                        filtered_ids.append(record['id'])
            if arg == "to":
                for record in all_books_dumped:
                    if int(record["published_year"].split("-")[0]) <= int(request.args.get("to")):
                        filtered_ids.append(record['id'])

        intersection_ids = list(set(intersection_ids) & set(filtered_ids))

    return intersection_ids


# ------ Getting the list of books from the database ------
@app.route("/books")
def searched_book():

    try:
        args_list = [arg for arg in request.args]
        if args_list:
            if set(args_list).issubset(filter_options_names):
                found_ids = filters()
                found_books = [record for record in books_schema.dump(all_books) if record['id'] in found_ids]
                return jsonify(found_books)
            else:
                return jsonify(error={"No such filter": f"Try one of these : {filter_options_names}"})
        else:
            return jsonify(books_schema.dump(all_books))

    except Exception as e:
        abort(404, error={"Exception": f"{e}"})


# ------ Checking the details of the book based on the id ------
@app.route("/books/<int:book_id>")
def book_details(book_id):

    the_book = Books.query.get(book_id)
    if the_book:
        the_book_dumped = book_schema.dump(the_book)
        return jsonify(the_book_dumped)

    else:
        abort(404, description="There is no such id in the database. Try another one.")


# ------ Adding a new book ------
@app.route("/books", methods=["POST"])
def add_new():

    try:
        title = request.json["title"]
        authors = request.json["authors"]
        acquired = request.json["acquired"]
        published_year = request.json["published_year"]
        thumbnail = request.json["thumbnail"]

        new_book = Books(title=title, authors=authors, acquired=acquired, published_year=published_year,
                         thumbnail=thumbnail, external_id=None)
        db.session.add(new_book)
        db.session.commit()
        return book_schema.jsonify(new_book)

    except Exception as e:
        return jsonify(error={"Exception": f"{e}"})


# ------ Editing an existing book ------
@app.route("/books/<int:book_id>", methods=["PATCH"])
def edit(book_id):

    edit_options = ["title", "authors", "acquired", "external_id", "published_year", "thumbnail"]

    try:
        book_to_edit = Books.query.get(book_id)
        for arg in request.args:
            if arg in edit_options:
                setattr(book_to_edit, arg, request.args[arg])
            else:
                return jsonify(error={"No such condition in database": "Try one of these : title, authors, acquired, external_id, published_year, thumbnail"})
            db.session.commit()
            return book_schema.jsonify(book_to_edit)

    except Exception as e:
        return jsonify(error={"Exception": f"{e}"})


# ------ Removing the book from the database ------
@app.route("/books/<int:book_id>", methods=["DELETE"])
def remove(book_id):

    try:
        book_to_delete = Books.query.get(book_id)
        if book_to_delete:
            db.session.delete(book_to_delete)
            db.session.commit()
            return jsonify(success={"Item removed": f"ID : {book_id}"})

        else:
            return jsonify(error={"No such id in the database": "Try another one"})

    except Exception as e:
        return jsonify(error={"Exception": f"{e}"})


# ------ Import books into database using the publicly available Google API ------
@app.route("/import", methods=["POST"])
def import_items():

    try:
        query_authors = request.json["authors"]
        response = requests.get(url=f"https://www.googleapis.com/books/v1/volumes?q={query_authors}+inauthor:{query_authors}&projection=lite")
        data = response.json()
        items = data["items"]

        number_of_imported_items = 0

        for item in items:
            # --- Checking if the item has been not already inserted ---
            item_external_id = item["id"]
            book_with_external_id = (
                db.session.query(Books)
                .filter_by(external_id=item_external_id)
                .first()
            )
            if book_with_external_id:
                book_to_delete = book_with_external_id
                db.session.delete(book_to_delete)
                db.session.commit()
            # --- Converting a list of authors into a string ---
            list_of_authors = [author for author in item["volumeInfo"]["authors"]]
            list_of_authors_string = ",".join(list_of_authors)

            # --- Calculating a number od imported items ---
            number_of_imported_items += 1

            # --- Adding new position into the database ---
            external_id=item["id"]
            title=item["volumeInfo"]["title"]
            authors=list_of_authors_string
            acquired=False
            published_year=item["volumeInfo"]["publishedDate"]

            # --- In some cases there is no 'imageLinks' ---
            if "imageLinks" in item["volumeInfo"]:
                thumbnail = item["volumeInfo"]["imageLinks"]["thumbnail"]
            else:
                thumbnail = None
            new_book = Books(title=title, authors=authors, acquired=acquired, published_year=published_year,
                                 thumbnail=thumbnail, external_id=external_id)
            db.session.add(new_book)
            db.session.commit()

        return jsonify({"Imported": f"{number_of_imported_items}"})


    except Exception as e:
        return jsonify(error={"Exception": f"{e}"})


if __name__ == "__main__":
    app.run(debug=True)
