from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
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

# --- Enabling SQLAlchemy connection to a database by creating a model ---
class Books(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(200), unique=True, nullable=True)
    title = db.Column(db.String(200), unique=False, nullable=False)
    authors = db.Column(db.String, unique=False, nullable=False)
    acquired = db.Column(db.Boolean, unique=False, nullable=False)
    published_year = db.Column(db.String(20), unique=False, nullable=False)
    thumbnail = db.Column(db.Text, unique=False, nullable=True)

    def __repr__(self):
        return (
            f"<Books {self.title} {self.author} {self.published_year}  {self.acquired}>"
        )

    def convert_to_dict(self):
        books_dictionary = {}
        for column in self.__table__.columns:
            books_dictionary[column.name] = getattr(self, column.name)
        return books_dictionary


db.create_all()


# ------ Home ------
@app.route("/")
def home():
    return '<h1>STX BookStore</h1>'


# ------ Api Specification ------
@app.route("/api_spec")
def api_spec():
    return jsonify(info={"version": "2022.05.16"})


# ------ Getting the list of books, filtering the results by title, author, publication year or the acquired state ------
def filters_applied(count):

    searched_books_ids = []

    query_title = request.args.get("title")
    if query_title:
        books = Books.query.filter(Books.title.contains(query_title)).all()
        for book in books:
            searched_books_ids.append(book.id)

    query_authors = request.args.get("authors")
    if query_authors:
        books = Books.query.filter(Books.authors.contains(query_authors)).all()
        for book in books:
            searched_books_ids.append(book.id)

    query_acquired_state = request.args.get("acquired")
    if query_acquired_state:
        books = Books.query.filter(Books.acquired.contains(query_acquired_state)).all()
        for book in books:
            searched_books_ids.append(book.id)

    query_published_year_from = request.args.get("from")
    query_published_year_to = request.args.get("to")

    if query_published_year_from:
        books_to_date_convert = [book.convert_to_dict() for book in Books.query.all()]
        for book in books_to_date_convert:
            book["published_year"] = int(book["published_year"].split("-")[0])
            if book["published_year"] >= int(query_published_year_from):
                searched_books_ids.append(book["id"])
    if query_published_year_to:
        books_to_date_convert = [book.convert_to_dict() for book in Books.query.all()]
        for book in books_to_date_convert:
            book["published_year"] = int(book["published_year"].split("-")[0])
            if book["published_year"] < int(query_published_year_to):
                searched_books_ids.append(book["id"])

    if searched_books_ids:
        dict_of_ids_counts = {item: searched_books_ids.count(item) for item in searched_books_ids}
        ids_of_found_book = [k for k, v in dict_of_ids_counts.items() if int(v) == count]
        Books.query.filter(Books.id.in_(ids_of_found_book)).all()
        return jsonify(searched_books=[book.convert_to_dict() for book in Books.query.filter(Books.id.in_(ids_of_found_book)).all()])

    else:
        return jsonify(error={"Not Found": "There is no such position among the books."})


# ------ Getting the list of books from the database ------
@app.route("/books")
def searched_book():

    # --- Checking whether the proper filters were applied ---
    filter_options = ["title", "authors", "acquired", "from", "to"]
    if request.args:
        count = len([arg for arg in request.args if arg in filter_options])
        if count:
            return filters_applied(count)
        else:
            return jsonify(error={"No such filter": f"Try one of these : {filter_options}"})

    else:
        all_books = db.session.query(Books).all()
        return jsonify(all_books=[book.convert_to_dict() for book in all_books])


# ------ Checking the details of the book based on the id ------
@app.route("/books/<int:book_id>")
def book_details(book_id):

    # --- Gathering all the ids from the database ---
    all_db_ids = db.session.scalars(db.session.query(Books.id)).all()

    if book_id in all_db_ids:
        the_book = Books.query.get(book_id)
        return jsonify(the_book.convert_to_dict())
    else:
        return jsonify(error={"No such id in the database": "Try onother one"})


# ------ Adding a new book ------
@app.route("/books", methods=["GET", "POST"])
def add_new():

    try:
        new_book = Books(
            title=request.args.get("title"),
            authors=request.args.get("authors"),
            acquired=bool(request.args.get("acquired")),
            published_year=request.args.get("published_year"),
        )
        db.session.add(new_book)
        db.session.commit()
        return jsonify(new_book.convert_to_dict())

    except Exception as e:
        return jsonify(error={"Exception": f"{e}"})


# ------ Editing an existing book ------
@app.route("/books/<int:book_id>", methods=["PATCH"])
def edit(book_id):

    # --- Gathering all the ids from the database ---
    all_db_ids = db.session.scalars(db.session.query(Books.id)).all()

    try:
        if book_id in all_db_ids and request.args:
            book_to_edit = Books.query.get(book_id)

            for arg in request.args:
                if arg == "title":
                    book_to_edit.title = request.args.get(arg)
                elif arg == "authors":
                    book_to_edit.authors = request.args.get(arg)
                elif arg == "acquired":
                    book_to_edit.acquired = bool(request.args.get(arg))
                elif arg == "external_id":
                    book_to_edit.external_id = request.args.get(arg)
                elif arg == "published_year":
                    book_to_edit.published_year = request.args.get(arg)
                elif arg == "thumbnail":
                    book_to_edit.thumbnail = request.args.get(arg)
                else:
                    return jsonify(error={"No such condition in database": "Try one of these : title, authors, acquired, external_id, published_year, thumbnail"})
            db.session.commit()
            return jsonify(book_to_edit.convert_to_dict())

        elif book_id in all_db_ids and not request.args:
            return jsonify(error={"No condition specified": "Try one of these : title, authors, acquired, external_id, published_year, thumbnail"})

        else:
            return jsonify(error={"No such id in the database": "Try onother one"})

    except Exception as e:
        return jsonify(error={"Exception": f"{e}"})


# ------ Removing the book from the database ------
@app.route("/books/<int:book_id>", methods=["DELETE"])
def remove(book_id):

    # --- Gathering all the ids from the database ---
    all_db_ids = db.session.scalars(db.session.query(Books.id)).all()

    try:
        if book_id in all_db_ids:
            book_to_delete = Books.query.get(book_id)
            db.session.delete(book_to_delete)
            db.session.commit()
            return jsonify(success={"Item removed": f"ID : {book_id}"})

        else:
            return jsonify(error={"No such id in the database": "Try onother one"})

    except Exception as e:
        return jsonify(error={"Exception": f"{e}"})


# ------ Import books into database using the publicly available Google API ------
@app.route("/import", methods=["GET", "POST"])
def import_items():

    try:
        for arg in request.args:
            if arg == "authors":
                query_authors = request.args.get("authors")
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
                    new_book = Books(
                        external_id=item["id"],
                        title=item["volumeInfo"]["title"],
                        authors=list_of_authors_string,
                        acquired=False,
                        published_year=item["volumeInfo"]["publishedDate"],
                    )
                    db.session.add(new_book)
                    db.session.commit()

                    # --- In some cases there is no 'imageLinks' ---
                    if "imageLinks" in item["volumeInfo"]:
                        new_book.thumbnail = item["volumeInfo"]["imageLinks"]["thumbnail"]
                    db.session.add(new_book)
                    db.session.commit()

                return jsonify({"Imported": f"{number_of_imported_items}"})

            else:
                return jsonify(error={"Wrong condition": "Try 'authors'"})

    except Exception as e:
        return jsonify(error={"Exception": f"{e}"})


if __name__ == "__main__":
    app.run()
