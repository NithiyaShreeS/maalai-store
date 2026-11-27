import sqlite3
from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
  password TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, material TEXT NOT NULL,
  price INTEGER NOT NULL CHECK(price>0),             -- paise
  stock INTEGER NOT NULL DEFAULT 0 CHECK(stock>=0),
  sizes TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
  image TEXT, stone TEXT NOT NULL DEFAULT '#9c1f55', design INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS wishlist(
  user_id INTEGER NOT NULL REFERENCES users(id), product_id INTEGER NOT NULL REFERENCES products(id),
  PRIMARY KEY(user_id, product_id));
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT, phone TEXT, address TEXT, city TEXT, pin TEXT,
  method TEXT NOT NULL CHECK(method IN ('razorpay','cod')),
  status TEXT NOT NULL, paid INTEGER NOT NULL DEFAULT 0,
  delivery INTEGER NOT NULL, total INTEGER NOT NULL,
  razorpay_order_id TEXT UNIQUE, razorpay_payment_id TEXT,
  stock_held INTEGER NOT NULL DEFAULT 1, note TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS order_items(
  id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  name TEXT NOT NULL, size TEXT NOT NULL, price INTEGER NOT NULL, qty INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY, name TEXT, reach TEXT, body TEXT,
  created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""

# name, category, material, rupees, stone, design, sizes, description
SEED = [
 ("Mullai bead necklace","Necklaces","Gold-plated brass",2450,"#f4f1e8",0,"","A close row of white beads on a gold finish chain."),
 ("Rani pendant chain","Necklaces","Sterling silver",3200,"#b32463",1,"","A single deep pink stone on a fine silver chain."),
 ("Temple coin haaram","Necklaces","Gold-plated brass",4800,"#c99a3d",2,"","A long strand of coin drops for sarees and functions."),
 ("Neelam drop necklace","Necklaces","Sterling silver",3900,"#24569c",0,"","Blue stones graded along a silver chain."),
 ("Classic dome jhumka","Earrings","Gold-plated brass",890,"#9c1f55",0,"","Bell-shaped jhumkas with a ring of tiny drops."),
 ("Pearl drop earrings","Earrings","Sterling silver",1250,"#f4f1e8",1,"","One pearl on a short silver drop."),
 ("Marakatham studs","Earrings","Gold-plated brass",650,"#16805a",2,"","Round green stone studs with a beaded gold edge."),
 ("Twin kada pair","Bangles","Gold-plated brass",1650,"#9c1f55",0,"2.4,2.6,2.8","Two broad bangles set with small pink stones."),
 ("Slim silver bangles","Bangles","Sterling silver",2800,"#cfd8dc",1,"2.4,2.6,2.8","Three plain bangles that stack with anything."),
 ("Emerald line bangle","Bangles","Gold-plated brass",1190,"#16805a",2,"2.4,2.6,2.8","A green stone line around the front."),
 ("Solitaire ring","Rings","Sterling silver",1450,"#dff3fb",0,"10,12,14,16","A clear cubic zirconia in a four-claw setting."),
 ("Kemp flower ring","Rings","Gold-plated brass",720,"#b3213f",1,"10,12,14,16","Red stones arranged as a small flower."),
 ("Plain band","Rings","Sterling silver",950,"#cfd8dc",2,"10,12,14,16","A smooth, slightly rounded everyday band."),
 ("Salangai anklet pair","Anklets","Sterling silver",2100,"#cfd8dc",0,"","Silver anklets with little bells."),
 ("Bead anklet pair","Anklets","Sterling silver",1350,"#b32463",1,"","Fine chains dotted with pink beads."),
]

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], isolation_level=None, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

def close_db(_=None):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    if not db.execute("SELECT 1 FROM products").fetchone():
        db.executemany(
            "INSERT INTO products(name,category,material,price,stone,design,sizes,description,stock)"
            " VALUES(?,?,?,?,?,?,?,?,10)",
            [(n,c,m,p*100,s,v,z,d) for n,c,m,p,s,v,z,d in SEED])
