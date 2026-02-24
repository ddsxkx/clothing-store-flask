from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
from datetime import datetime
import traceback
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Берем секретный ключ из переменных окружения
app.secret_key = os.getenv('SECRET_KEY')

# Создаем конфиг для БД из переменных окружения
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_DATABASE'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

def get_db_connection():
    """Функция для подключения к базе данных"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f" Ошибка подключения к БД: {e}")
        return None


def get_current_user_id():
    """Получаем ID текущего пользователя из сессии"""
    return session.get('user_id')


def get_current_user_info():
    """Получаем информацию о текущем пользователе"""
    user_id = get_current_user_id()
    if not user_id:
        return None

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, email, имя, фамилия FROM "user" WHERE id = %s;', (user_id,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            return {
                'id': user[0],
                'email': user[1],
                'имя': user[2],
                'фамилия': user[3]
            }
    except Exception as e:
        print(f"Ошибка при получении информации о пользователе: {e}")

    return None


# Главная страница
@app.route('/')
def index():
    try:
        conn = get_db_connection()
        if not conn:
            return render_template('index.html', products=[], reviews=[])

        cur = conn.cursor()

        # Получаем популярные товары
        cur.execute('''
            SELECT p.id, p.название, p.цена, p.цвет, c.название as категория, p.изображение 
            FROM product p 
            JOIN category c ON p.категория_id = c.id 
            WHERE p.активен = True 
            LIMIT 4;
        ''')
        products = cur.fetchall()

        # Получаем одобренные отзывы с информацией о пользователях и товарах
        cur.execute('''
            SELECT 
                r.комментарий,
                r.рейтинг,
                r.дата_создания,
                u.имя,
                u.фамилия,
                p.название as товар
            FROM review r
            JOIN "user" u ON r.пользователь_id = u.id
            JOIN product p ON r.товар_id = p.id
            WHERE r.одобрен = true
            ORDER BY r.дата_создания DESC
            LIMIT 3;
        ''')
        reviews = cur.fetchall()

        # выводим информацию об отзывах
        print(f"=== ОТЗЫВЫ НА ГЛАВНОЙ ===")
        print(f"Найдено отзывов: {len(reviews)}")
        for i, review in enumerate(reviews):
            print(f"Отзыв {i + 1}: {review[3]} {review[4]} - {review[5]} - Рейтинг: {review[1]}")

        cur.close()
        conn.close()

        return render_template('index.html', products=products, reviews=reviews)

    except Exception as e:
        print(f"Ошибка БД в главной странице: {e}")
        import traceback
        traceback.print_exc()
        return render_template('index.html', products=[], reviews=[])

# Добавление отзыва
@app.route('/add_review/<int:product_id>', methods=['POST'])
def add_review(product_id):
    user_id = get_current_user_id()
    if not user_id:
        flash('Для добавления отзыва необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    try:
        rating = int(request.form.get('rating'))
        comment = request.form.get('comment')

        if not rating or not comment:
            flash('Заполните все поля', 'error')
            return redirect(url_for('product_detail', product_id=product_id))

        conn = get_db_connection()
        cur = conn.cursor()

        # Находим максимальный ID
        cur.execute('SELECT COALESCE(MAX(id), 0) FROM review;')
        max_id = cur.fetchone()[0]
        new_id = max_id + 1

        # Добавляем отзыв (по умолчанию не одобрен)
        cur.execute('''
            INSERT INTO review (id, пользователь_id, товар_id, рейтинг, комментарий, дата_создания, одобрен)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (new_id, user_id, product_id, rating, comment, datetime.now(), False))

        conn.commit()
        cur.close()
        conn.close()

        flash('Спасибо за ваш отзыв! Он будет опубликован после проверки.', 'success')
        return redirect(url_for('product_detail', product_id=product_id))

    except Exception as e:
        print(f"Ошибка при добавлении отзыва: {e}")
        flash('Ошибка при добавлении отзыва', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
# Страница регистрации
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            # Получаем данные из формы
            email = request.form['email']
            password = request.form['password']
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            phone = request.form.get('phone', '')
            address = request.form.get('address', '')

            # Проверяем обязательные поля
            if not email or not password or not first_name or not last_name:
                flash('Заполните все обязательные поля', 'error')
                return render_template('register.html')

            conn = get_db_connection()
            if not conn:
                flash('Ошибка подключения к базе данных', 'error')
                return render_template('register.html')

            cur = conn.cursor()

            # Проверяем, нет ли уже пользователя с таким email
            cur.execute('SELECT id FROM "user" WHERE email = %s;', (email,))
            existing_user = cur.fetchone()

            if existing_user:
                flash('Пользователь с таким email уже существует', 'error')
                return render_template('register.html')

            # Хэшируем пароль
            hashed_password = generate_password_hash(password)

            # Находим максимальный ID
            cur.execute('SELECT COALESCE(MAX(id), 0) FROM "user";')
            max_id = cur.fetchone()[0]
            new_id = max_id + 1

            # Создаем нового пользователя
            cur.execute('''
                INSERT INTO "user" (id, email, пароль, имя, фамилия, телефон, адрес, дата_регистрации) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            ''', (new_id, email, hashed_password, first_name, last_name, phone, address, datetime.now()))

            conn.commit()
            flash('Регистрация успешна! Теперь вы можете войти.', 'success')

            cur.close()
            conn.close()

            return redirect(url_for('login'))

        except Exception as e:
            print(f"Ошибка при регистрации: {e}")
            flash('Ошибка при регистрации', 'error')

    return render_template('register.html')



# Страница входа
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            email = request.form['email']
            password = request.form['password']

            if not email or not password:
                flash('Введите email и пароль', 'error')
                return render_template('login.html')

            conn = get_db_connection()
            if not conn:
                flash('Ошибка подключения к базе данных', 'error')
                return render_template('login.html')

            cur = conn.cursor()

            # Ищем пользователя по email
            cur.execute('SELECT id, email, пароль, имя, фамилия FROM "user" WHERE email = %s;', (email,))
            user = cur.fetchone()

            if user:
                stored_password = user[2]

                # Проверяем, хэширован ли уже пароль
                # Если пароль не начинается с типичного префикса хэша, считаем его незашифрованным
                if stored_password.startswith('pbkdf2:') or stored_password.startswith(
                        'scrypt:') or stored_password.startswith('$2b$'):
                    # Пароль хэширован, проверяем через check_password_hash
                    if check_password_hash(stored_password, password):
                        # Успешный вход
                        session['user_id'] = user[0]
                        session['user_email'] = user[1]
                        session['user_name'] = user[3]

                        flash(f'Добро пожаловать, {user[3]}!', 'success')

                        cur.close()
                        conn.close()

                        return redirect(url_for('index'))
                    else:
                        flash('Неверный email или пароль', 'error')
                else:
                    # Пароль не хэширован, проверяем напрямую
                    if stored_password == password:
                        # Успешный вход, но нужно обновить пароль на хэшированный
                        hashed_password = generate_password_hash(password)
                        cur.execute('UPDATE "user" SET пароль = %s WHERE id = %s;', (hashed_password, user[0]))
                        conn.commit()

                        # Устанавливаем сессию
                        session['user_id'] = user[0]
                        session['user_email'] = user[1]
                        session['user_name'] = user[3]

                        flash(f'Добро пожаловать, {user[3]}! Пароль обновлен для безопасности.', 'success')

                        cur.close()
                        conn.close()

                        return redirect(url_for('index'))
                    else:
                        flash('Неверный email или пароль', 'error')
            else:
                flash('Неверный email или пароль', 'error')

            cur.close()
            conn.close()

        except Exception as e:
            print(f"Ошибка при входе: {e}")
            print(traceback.format_exc())
            flash('Ошибка при входе', 'error')

    return render_template('login.html')

# Выход
@app.route('/logout')
def logout():
    session.clear()
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('index'))


# Добавление товара в корзину (сохраняем в БД)
@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    user_id = get_current_user_id()
    if not user_id:
        flash('Для добавления товаров в корзину необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    try:
        print(f"=== ПОПЫТКА ДОБАВИТЬ В КОРЗИНУ ===")
        print(f"Товар ID: {product_id}, Пользователь ID: {user_id}")

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return redirect(request.referrer or url_for('index'))

        cur = conn.cursor()

        # 1. Проверяем существование пользователя
        cur.execute('SELECT id, имя FROM "user" WHERE id = %s;', (user_id,))
        user = cur.fetchone()
        if not user:
            print(f" Пользователь с ID {user_id} не найден!")
            flash('Пользователь не найден', 'error')
            return redirect(request.referrer or url_for('index'))
        print(f" Пользователь найден: {user[1]}")

        # 2. Проверяем существование товара
        cur.execute('SELECT id, название, цена, активен FROM product WHERE id = %s;', (product_id,))
        product = cur.fetchone()

        if not product:
            print("❌ Товар не найден!")
            flash('Товар не найден', 'error')
            return redirect(request.referrer or url_for('index'))

        print(f"✅ Товар найден: {product[1]}, цена: {product[2]}, активен: {product[3]}")

        if not product[3]:  # если не активен
            print("❌ Товар не активен!")
            flash('Товар временно недоступен', 'error')
            return redirect(request.referrer or url_for('index'))

        # 3. Проверяем, есть ли товар уже в корзине пользователя
        cur.execute('''
            SELECT id, количество FROM cart 
            WHERE пользователь_id = %s AND товар_id = %s;
        ''', (user_id, product_id))

        existing_item = cur.fetchone()

        if existing_item:
            # Увеличиваем количество
            new_quantity = existing_item[1] + 1
            cur.execute('''
                UPDATE cart SET количество = %s, дата_добавления = %s 
                WHERE id = %s;
            ''', (new_quantity, datetime.now(), existing_item[0]))
            print(f"🔄 Увеличили количество товара до {new_quantity}")
        else:
            # Добавляем новый товар в корзину
            # Сначала найдем максимальный ID в корзине
            cur.execute('SELECT COALESCE(MAX(id), 0) FROM cart;')
            max_id = cur.fetchone()[0]
            new_id = max_id + 1

            cur.execute('''
                INSERT INTO cart (id, пользователь_id, товар_id, количество, дата_добавления) 
                VALUES (%s, %s, %s, %s, %s);
            ''', (new_id, user_id, product_id, 1, datetime.now()))
            print(f"✅ Добавили новый товар в корзину. ID записи: {new_id}")

        conn.commit()
        print("✅ Изменения сохранены в БД")
        flash('Товар добавлен в корзину!', 'success')

        # Проверим что действительно добавилось
        cur.execute('SELECT COUNT(*) FROM cart WHERE пользователь_id = %s;', (user_id,))
        cart_count = cur.fetchone()[0]
        print(f"📊 Теперь в корзине пользователя {user_id} товаров: {cart_count}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА при добавлении в корзину:")
        print(traceback.format_exc())
        flash('Ошибка при добавлении товара в корзину', 'error')

    return redirect(request.referrer or url_for('index'))


# Страница корзины
@app.route('/cart')
def view_cart():
    user_id = get_current_user_id()
    if not user_id:
        flash('Для просмотра корзины необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    try:
        print(f"=== ЗАПРОС КОРЗИНЫ ===")
        print(f"Пользователь: {user_id}")

        conn = get_db_connection()
        if not conn:
            print("❌ Нет подключения к БД")
            return render_template('cart.html', cart_items=[], total=0)

        cur = conn.cursor()

        # Сначала проверим простой запрос
        cur.execute('SELECT COUNT(*) FROM cart WHERE пользователь_id = %s;', (user_id,))
        simple_count = cur.fetchone()[0]
        print(f"📊 Простой подсчет товаров в корзине: {simple_count}")

        # Получаем корзину пользователя с информацией о товарах
        cur.execute('''
            SELECT 
                c.id as cart_id,
                c.товар_id,
                c.количество,
                c.дата_добавления,
                p.название,
                p.цена,
                p.цвет,
                cat.название as категория
            FROM cart c
            JOIN product p ON c.товар_id = p.id
            JOIN category cat ON p.категория_id = cat.id
            WHERE c.пользователь_id = %s
            ORDER BY c.дата_добавления DESC;
        ''', (user_id,))

        cart_items = cur.fetchall()

        print(f" Найдено товаров в корзине: {len(cart_items)}")
        for item in cart_items:
            print(f"   - {item[4]} (количество: {item[2]})")

        # Рассчитываем общую сумму
        total = sum(item[5] * item[2] for item in cart_items)  # цена * количество

        cur.close()
        conn.close()

        return render_template('cart.html', cart_items=cart_items, total=total)

    except Exception as e:
        print(f"❌ Ошибка при загрузке корзины: {e}")
        print(traceback.format_exc())
        return render_template('cart.html', cart_items=[], total=0)


# Удаление товара из корзины
@app.route('/remove_from_cart/<int:cart_item_id>')
def remove_from_cart(cart_item_id):
    user_id = get_current_user_id()
    if not user_id:
        flash('Для управления корзиной необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        print(f"Удаляем товар из корзины: cart_item_id = {cart_item_id}")

        cur.execute('DELETE FROM cart WHERE id = %s AND пользователь_id = %s;',
                    (cart_item_id, user_id))

        conn.commit()
        flash('Товар удален из корзины', 'success')

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Ошибка при удалении из корзины: {e}")
        flash('Ошибка при удалении товара', 'error')

    return redirect(url_for('view_cart'))


# Изменение количества товара в корзине
@app.route('/update_cart_quantity/<int:cart_item_id>', methods=['POST'])
def update_cart_quantity(cart_item_id):
    user_id = get_current_user_id()
    if not user_id:
        flash('Для управления корзиной необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    try:
        new_quantity = int(request.form['quantity'])

        print(f"Обновляем количество товара {cart_item_id} на {new_quantity}")

        if new_quantity <= 0:
            # Если количество 0 или меньше, удаляем товар
            return redirect(url_for('remove_from_cart', cart_item_id=cart_item_id))

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute('''
            UPDATE cart SET количество = %s, дата_добавления = %s 
            WHERE id = %s AND пользователь_id = %s;
        ''', (new_quantity, datetime.now(), cart_item_id, user_id))

        conn.commit()
        flash('Количество товара обновлено', 'success')

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Ошибка при обновлении корзины: {e}")
        flash('Ошибка при обновлении количества', 'error')

    return redirect(url_for('view_cart'))


# Каталог товаров с фильтрацией по категориям
@app.route('/catalog')
@app.route('/catalog/<int:category_id>')
def catalog(category_id=None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Получаем все активные категории
        cur.execute('''
            SELECT id, название, родительская_категория 
            FROM category 
            WHERE активна = True 
            ORDER BY название;
        ''')
        categories = cur.fetchall()

        # Получаем товары
        if category_id == 1:  # ID категории "Вся одежда"
            # Показываем ВСЕ товары
            cur.execute('''
                SELECT p.id, p.название, p.цена, p.цвет, c.название as категория, p.изображение  
                FROM product p 
                JOIN category c ON p.категория_id = c.id 
                WHERE p.активен = True;
            ''')
        elif category_id:
            # Показываем товары только этой категории
            cur.execute('''
                SELECT p.id, p.название, p.цена, p.цвет, c.название as категория, p.изображение  
                FROM product p 
                JOIN category c ON p.категория_id = c.id 
                WHERE p.активен = True AND p.категория_id = %s;
            ''', (category_id,))
        else:
            # Главная страница каталога - тоже показываем все товары
            cur.execute('''
                SELECT p.id, p.название, p.цена, p.цвет, c.название as категория, p.изображение  
                FROM product p 
                JOIN category c ON p.категория_id = c.id 
                WHERE p.активен = True;
            ''')

        products = cur.fetchall()

        # Получаем название текущей категории
        current_category_name = "Все товары"
        if category_id:
            cur.execute('SELECT название FROM category WHERE id = %s;', (category_id,))
            category_result = cur.fetchone()
            if category_result:
                current_category_name = category_result[0]

        cur.close()
        conn.close()

        return render_template('catalog.html',
                               products=products,
                               categories=categories,
                               current_category_id=category_id,
                               current_category_name=current_category_name)

    except Exception as e:
        print(f"Ошибка БД: {e}")
        return render_template('catalog.html', products=[], categories=[])


# Страница товара
@app.route('/product/<int:product_id>')
def product_detail(product_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Получаем информацию о товаре (без описания, т.к. его нет в таблице)
        cur.execute('''
            SELECT p.id, p.название, p.цена, p.цвет, p.размер, p.изображение, c.название as категория 
            FROM product p 
            JOIN category c ON p.категория_id = c.id 
            WHERE p.id = %s AND p.активен = True;
        ''', (product_id,))
        product = cur.fetchone()

        if not product:
            flash('Товар не найден', 'error')
            return redirect(url_for('catalog'))

        cur.close()
        conn.close()

        return render_template('product_detail.html', product=product)

    except Exception as e:
        print(f"Ошибка при загрузке товара: {e}")
        flash('Ошибка при загрузке товара', 'error')
        return redirect(url_for('catalog'))


# Страница всех категорий
@app.route('/categories')
def categories():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # только нужные поля
        cur.execute('''
            SELECT 
                id, 
                название, 
                описание, 
                родительская_категория
            FROM category 
            WHERE активна = True 
            ORDER BY родительская_категория NULLS FIRST, название;
        ''')
        categories = cur.fetchall()

        cur.close()
        conn.close()

        return render_template('categories.html', categories=categories)

    except Exception as e:
        print(f"Ошибка БД в категориях: {e}")
        return render_template('categories.html', categories=[])



# Оформление заказа
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    user_id = get_current_user_id()
    if not user_id:
        flash('Для оформления заказа необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return redirect(url_for('view_cart'))

        cur = conn.cursor()

        # Проверяем, есть ли товары в корзине
        cur.execute('SELECT COUNT(*) FROM cart WHERE пользователь_id = %s;', (user_id,))
        cart_count = cur.fetchone()[0]

        print(f"=== ОТЛАДКА CHECKOUT ===")
        print(f"Пользователь: {user_id}, товаров в корзине: {cart_count}")

        if cart_count == 0:
            flash('Корзина пуста!', 'error')
            return redirect(url_for('view_cart'))

        if request.method == 'POST':
            # Обработка оформления заказа
            shipping_address = request.form.get('shipping_address')

            if not shipping_address:
                flash('Введите адрес доставки', 'error')
                return redirect(url_for('checkout'))

            # Получаем товары из корзины для расчета суммы
            cur.execute('''
                SELECT 
                    c.товар_id,
                    c.количество,
                    p.цена,
                    p.название
                FROM cart c
                JOIN product p ON c.товар_id = p.id
                WHERE c.пользователь_id = %s
            ''', (user_id,))
            cart_items = cur.fetchall()

            print(f"Товары в корзине: {cart_items}")

            total_amount = sum(item[2] * item[1] for item in cart_items)
            print(f"Общая сумма: {total_amount}")

            # Создаем номер заказа
            order_number = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            print(f"Номер заказа: {order_number}")

            # Находим максимальный ID для заказа
            cur.execute('SELECT COALESCE(MAX(id), 0) FROM "order";')
            max_order_id = cur.fetchone()[0]
            new_order_id = max_order_id + 1
            print(f"Новый ID заказа: {new_order_id}")

            # Создаем заказ
            cur.execute('''
                INSERT INTO "order" (id, пользователь_id, номер_заказа, статус, общая_сумма, адрес_доставки, дата_создания)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (new_order_id, user_id, order_number, 'создан', total_amount, shipping_address, datetime.now()))

            print(f"Заказ создан в таблице 'order'")

            # Сохраняем товары в таблицу order_items
            for item in cart_items:
                product_id, quantity, price, product_name = item
                print(f"Сохраняем товар: {product_name} (ID: {product_id}), количество: {quantity}, цена: {price}")

                cur.execute('''
                    INSERT INTO order_items (order_id, product_id, quantity, price_at_order)
                    VALUES (%s, %s, %s, %s)
                ''', (new_order_id, product_id, quantity, price))

            print(f"Товары сохранены в order_items")

            # Очищаем корзину
            cur.execute('DELETE FROM cart WHERE пользователь_id = %s;', (user_id,))
            print(f"Корзина очищена")

            conn.commit()
            print(f"Транзакция завершена успешно")

            flash('Заказ успешно создан! Теперь вы можете оплатить его.', 'success')

            cur.close()
            conn.close()

            # Перенаправляем на страницу оплаты
            return redirect(url_for('payment', order_id=new_order_id))

        else:
            # GET запрос - показываем форму оформления заказа
            # Получаем товары из корзины для отображения
            cur.execute('''
                SELECT 
                    c.id as cart_id,
                    c.товар_id,
                    c.количество,
                    p.название,
                    p.цена,
                    p.цвет
                FROM cart c
                JOIN product p ON c.товар_id = p.id
                WHERE c.пользователь_id = %s
            ''', (user_id,))
            cart_items = cur.fetchall()

            total_amount = sum(item[4] * item[2] for item in cart_items)

            # Получаем адрес пользователя по умолчанию
            cur.execute('SELECT адрес FROM "user" WHERE id = %s;', (user_id,))
            user_address = cur.fetchone()
            default_address = user_address[0] if user_address else ''

            cur.close()
            conn.close()

            return render_template('checkout.html',
                                   cart_items=cart_items,
                                   total_amount=total_amount,
                                   default_address=default_address)

    except Exception as e:
        print(f" КРИТИЧЕСКАЯ ОШИБКА при оформлении заказа: {e}")
        import traceback
        traceback.print_exc()
        flash('Ошибка при оформлении заказа', 'error')
        return redirect(url_for('view_cart'))


@app.route('/api/order/<int:order_id>/items')
def api_order_items(order_id):
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Проверяем что заказ принадлежит пользователю
        cur.execute('SELECT id FROM "order" WHERE id = %s AND пользователь_id = %s', (order_id, user_id))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'Order not found'}), 404

        # Получаем товары заказа
        cur.execute('''
            SELECT 
                p.название AS product_name,
                oi.quantity,
                oi.price_at_order,
                (oi.quantity * oi.price_at_order) as total,
                COALESCE(p.изображение, '/static/images/placeholder.jpg') as image
            FROM order_items oi
            LEFT JOIN product p ON oi.product_id = p.id
            WHERE oi.order_id = %s
            ORDER BY oi.id
        ''', (order_id,))

        items = []
        for row in cur.fetchall():
            items.append({
                'name': row[0],
                'quantity': row[1],
                'price': float(row[2]),
                'total': float(row[3]),
                'image': row[4]
            })

        # Получаем номер заказа
        cur.execute('SELECT номер_заказа FROM "order" WHERE id = %s', (order_id,))
        order_number_result = cur.fetchone()
        order_number = order_number_result[0] if order_number_result else f'Заказ #{order_id}'

        cur.close()
        conn.close()

        return jsonify({
            'order_number': order_number,
            'items': items,
            'total': sum(item['total'] for item in items)
        })  # ← ЗАКРЫВАЮЩАЯ СКОБКА ДЛЯ jsonify() И ЗАПЯТАЯ

    except Exception as e:
        print(f"Ошибка в API order items: {e}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
# Страница "Мои заказы"
@app.route('/my_orders')
def my_orders():
    user_id = get_current_user_id()
    if not user_id:
        flash('Для просмотра заказов необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Получаем заказы пользователя
        cur.execute('''
            SELECT 
                o.id,
                o.номер_заказа,
                o.статус,
                o.общая_сумма,
                o.адрес_доставки,
                o.дата_создания
            FROM "order" o
            WHERE o.пользователь_id = %s 
            ORDER BY o.дата_создания DESC;
        ''', (user_id,))

        orders_data = cur.fetchall()

        # Для каждого заказа получаем его товары
        orders_with_items = []
        for order in orders_data:
            order_id = order[0]

            try:
                # Получаем товары этого заказа
                cur.execute('''
                    SELECT 
                        p.название AS product_name,
                        oi.quantity,
                        oi.price_at_order,
                        (oi.quantity * oi.price_at_order) as total,
                        p.изображение
                    FROM order_items oi
                    LEFT JOIN product p ON oi.product_id = p.id
                    WHERE oi.order_id = %s
                    ORDER BY oi.id;
                ''', (order_id,))

                items = cur.fetchall()
            except Exception as e:
                # Если таблицы order_items нет или другая ошибка
                print(f"Ошибка при получении товаров для заказа {order_id}: {e}")
                items = []

            # Создаем словарь с заказом и его товарами
  
            order_dict = {
                'id': order[0],
                'number': order[1],
                'status': order[2],
                'total': float(order[3]) if order[3] else 0.0,
                'address': order[4] if order[4] else 'Адрес не указан',
                'date': order[5],
                'order_items': items  # Изменено с 'items' на 'order_items'
            }
            orders_with_items.append(order_dict)

        cur.close()
        conn.close()

        print(f"=== ОТЛАДКА MY_ORDERS ===")
        print(f"Заказов найдено: {len(orders_with_items)}")

        total_sum = sum(order['total'] for order in orders_with_items)
        print(f"Общая сумма всех заказов: {total_sum}")

        return render_template('my_orders.html', orders=orders_with_items)

    except Exception as e:
        print(f"Ошибка при загрузке заказов: {e}")
        import traceback
        traceback.print_exc()
        flash('Ошибка при загрузке заказов', 'error')
        return render_template('my_orders.html', orders=[])
# Функция для получения деталей заказа с товарами
def get_order_details(order_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Получаем информацию о заказе
        cur.execute('''
            SELECT 
                o.id,
                o.номер_заказа,
                o.статус,
                o.общая_сумма,
                o.адрес_доставки,
                o.дата_создания
            FROM "order" o
            WHERE o.id = %s
        ''', (order_id,))
        order = cur.fetchone()

        # Получаем товары в заказе
        cur.execute('''
            SELECT 
                oi.product_id,
                p.название AS product_name,
                oi.quantity,
                oi.price_at_order,
                (oi.quantity * oi.price_at_order) as total,
                p.изображение
            FROM order_items oi
            LEFT JOIN product p ON oi.product_id = p.id
            WHERE oi.order_id = %s
            ORDER BY oi.id
        ''', (order_id,))
        items = cur.fetchall()

        cur.close()
        conn.close()

        return order, items

    except Exception as e:
        print(f"Ошибка при получении деталей заказа: {e}")
        return None, []

# Детали заказа
@app.route('/order/<int:order_id>')
def order_details(order_id):
    # Используем current_user_id вместо user_id чтобы избежать конфликта имен
    current_user_id = get_current_user_id()
    if not current_user_id:
        flash('Для просмотра заказа необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    try:

        connection = get_db_connection()

        cursor = connection.cursor()

        # Проверяем что заказ принадлежит пользователю
        cursor.execute('''
            SELECT 
                o.id,
                o.номер_заказа,
                o.статус,
                o.общая_сумма,
                o.адрес_доставки,
                o.дата_создания,
                p.транзакция_id,
                p.способ_оплаты,
                p.дата_оплаты
            FROM "order" o
            LEFT JOIN payment p ON o.id = p.заказ_id
            WHERE o.id = %s AND o.пользователь_id = %s;
        ''', (order_id, current_user_id))

        order = cursor.fetchone()

        if not order:
            flash('Заказ не найден', 'error')
            return redirect(url_for('my_orders'))

        cursor.close()
        connection.close()

        return render_template('order_details.html', order=order)

    except Exception as error:  # Используем error вместо e
        print(f"Ошибка при загрузке деталей заказа: {error}")
        flash('Ошибка при загрузке деталей заказа', 'error')
        return redirect(url_for('my_orders'))


# Страница оплаты
@app.route('/payment/<int:order_id>', methods=['GET', 'POST'])
def payment(order_id):
    user_id = get_current_user_id()
    if not user_id:
        flash('Для оплаты заказа необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Проверяем, что заказ принадлежит пользователю
        cur.execute('''
            SELECT id, номер_заказа, общая_сумма, статус 
            FROM "order" 
            WHERE id = %s AND пользователь_id = %s;
        ''', (order_id, user_id))
        order = cur.fetchone()

        if not order:
            flash('Заказ не найден', 'error')
            return redirect(url_for('index'))

        if request.method == 'POST':
            # Обработка оплаты
            payment_method = request.form.get('payment_method')

            if not payment_method:
                flash('Выберите способ оплаты', 'error')
                return redirect(url_for('payment', order_id=order_id))

            # Находим максимальный ID для платежа
            cur.execute('SELECT COALESCE(MAX(id), 0) FROM payment;')
            max_payment_id = cur.fetchone()[0]
            new_payment_id = max_payment_id + 1

            # Создаем транзакцию
            transaction_id = f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # Создаем запись о платеже
            cur.execute('''
                INSERT INTO payment (id, заказ_id, способ_оплаты, статус, сумма, дата_оплаты, транзакция_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (new_payment_id, order_id, payment_method, 'успешно', order[2], datetime.now(), transaction_id))

            # Обновляем статус заказа
            cur.execute('''
                UPDATE "order" SET статус = 'оплачен' WHERE id = %s;
            ''', (order_id,))

            conn.commit()
            cur.close()
            conn.close()

            flash('Оплата прошла успешно! Спасибо за покупку!', 'success')
            return redirect(url_for('order_success', order_id=order_id))

        else:
            # GET запрос - показываем страницу оплаты
            cur.close()
            conn.close()
            return render_template('payment.html', order=order)

    except Exception as e:
        print(f"Ошибка при обработке оплаты: {e}")
        print(traceback.format_exc())
        flash('Ошибка при обработке оплаты', 'error')
        return redirect(url_for('index'))


# Страница успешного заказа
@app.route('/order_success/<int:order_id>')
def order_success(order_id):
    user_id = get_current_user_id()
    if not user_id:
        flash('Для просмотра заказа необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Получаем информацию о заказе и платеже
        cur.execute('''
            SELECT 
                o.номер_заказа,
                o.общая_сумма,
                o.адрес_доставки,
                o.дата_создания,
                p.транзакция_id,
                p.дата_оплаты
            FROM "order" o
            LEFT JOIN payment p ON o.id = p.заказ_id
            WHERE o.id = %s AND o.пользователь_id = %s;
        ''', (order_id, user_id))
        order_info = cur.fetchone()

        if not order_info:
            flash('Заказ не найден', 'error')
            return redirect(url_for('index'))

        cur.close()
        conn.close()

        return render_template('order_success.html', order=order_info)

    except Exception as e:
        print(f"Ошибка при загрузке страницы успеха: {e}")
        flash('Ошибка при загрузке информации о заказе', 'error')
        return redirect(url_for('index'))

@app.route('/admin/stats')
def admin_stats():
    conn = get_db_connection()
    cur = conn.cursor()

    #  Оконный запрос 1 — рейтинг товаров по продажам
    cur.execute('''
        SELECT 
            p.название AS product_name,
            SUM(oi.quantity) AS sold,
            RANK() OVER (ORDER BY SUM(oi.quantity) DESC) AS sales_rank
        FROM order_items oi
        JOIN product p ON oi.product_id = p.id
        GROUP BY p.id, p.название
        ORDER BY sales_rank;
    ''')
    product_stats = cur.fetchall()

    # Оконный запрос 2 — средний чек по заказам
    cur.execute('''
        SELECT 
            id,
            номер_заказа,
            общая_сумма,
            AVG(общая_сумма) OVER () AS avg_order_amount
        FROM "order";
    ''')
    order_stats = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'admin_stats.html',
        product_stats=product_stats,
        order_stats=order_stats
    )


# Добавьте в app.py после существующих маршрутов, но перед if __name__ == '__main__':

@app.route('/sql_queries')
def sql_queries():
    """Страница с SQL запросами"""
    user_id = get_current_user_id()
    if not user_id:
        flash('Для просмотра SQL запросов необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Для запроса 7 - получаем список категорий для выпадающего списка
        cur.execute("SELECT id, название FROM category WHERE активна = True ORDER BY название;")
        categories = cur.fetchall()

        # Для запроса 8 - получаем список статусов заказов
        cur.execute("SELECT DISTINCT статус FROM \"order\" ORDER BY статус;")
        statuses = cur.fetchall()

        # Для запроса 9 - получаем список пользователей
        cur.execute("SELECT id, имя, фамилия FROM \"user\" ORDER BY фамилия, имя;")
        users = cur.fetchall()

        cur.close()
        conn.close()

        return render_template('sql_queries.html',
                               categories=categories,
                               statuses=statuses,
                               users=users)

    except Exception as e:
        print(f"Ошибка при загрузке страницы SQL запросов: {e}")
        flash('Ошибка при загрузке страницы', 'error')
        return redirect(url_for('index'))


@app.route('/execute_query/<int:query_id>', methods=['GET', 'POST'])
def execute_query(query_id):
    """Выполнение конкретного SQL запроса"""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Требуется авторизация'}), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        results = []
        columns = []

        if query_id == 1:
            # Запрос 1: Статический - Топ товаров по продажам
            sql = '''
            SELECT 
                p.название AS "Название товара",
                SUM(oi.quantity) AS "Продано, шт.",
                RANK() OVER (ORDER BY SUM(oi.quantity) DESC) AS "Ранг"
            FROM order_items oi
            JOIN product p ON oi.product_id = p.id
            WHERE p.активен = True
            GROUP BY p.id, p.название
            ORDER BY "Продано, шт." DESC
            LIMIT 10;
            '''

        elif query_id == 2:
            # Запрос 2: Статический - Средняя оценка товаров
            sql = '''
            SELECT 
                p.название AS "Товар",
                ROUND(AVG(r.рейтинг), 2) AS "Средний рейтинг",
                COUNT(r.id) AS "Количество отзывов"
            FROM review r
            JOIN product p ON r.товар_id = p.id
            WHERE r.одобрен = True
            GROUP BY p.id, p.название
            HAVING COUNT(r.id) >= 2
            ORDER BY "Средний рейтинг" DESC;
            '''

        elif query_id == 3:
            # Запрос 3: Статический - Пользователи с наибольшим количеством заказов
            sql = '''
            SELECT 
                u.имя || ' ' || u.фамилия AS "Покупатель",
                COUNT(o.id) AS "Количество заказов",
                SUM(o.общая_сумма) AS "Общая сумма покупок"
            FROM "order" o
            JOIN "user" u ON o.пользователь_id = u.id
            GROUP BY u.id, u.имя, u.фамилия
            ORDER BY "Количество заказов" DESC
            LIMIT 8;
            '''

        elif query_id == 4:
            # Запрос 4: С оконной функцией - Рейтинг товаров в каждой категории
            sql = '''
            SELECT 
                c.название AS "Категория",
                p.название AS "Товар",
                SUM(oi.quantity) AS "Продано, шт.",
                RANK() OVER (PARTITION BY c.id ORDER BY SUM(oi.quantity) DESC) AS "Ранг в категории"
            FROM order_items oi
            JOIN product p ON oi.product_id = p.id
            JOIN category c ON p.категория_id = c.id
            WHERE p.активен = True
            GROUP BY c.id, c.название, p.id, p.название
            ORDER BY c.название, "Продано, шт." DESC;
            '''

        elif query_id == 5:
            # Запрос 5: С оконной функцией - Сравнение с средним чеком
            sql = '''
            SELECT 
                o.номер_заказа AS "Номер заказа",
                o.общая_сумма AS "Сумма заказа",
                ROUND(AVG(o.общая_сумма) OVER (), 2) AS "Средний чек",
                o.общая_сумма - ROUND(AVG(o.общая_сумма) OVER (), 2) AS "Отклонение от среднего"
            FROM "order" o
            ORDER BY o.общая_сумма DESC;
            '''

        elif query_id == 6:
            # Запрос 6: Параметризованный - Товары в указанном ценовом диапазоне
            min_price = request.args.get('min_price', 0)
            max_price = request.args.get('max_price', 10000)

            sql = '''
            SELECT 
                p.название AS "Название товара",
                p.цена AS "Цена",
                c.название AS "Категория",
                p.цвет AS "Цвет"
            FROM product p
            JOIN category c ON p.категория_id = c.id
            WHERE p.активен = True 
                AND p.цена BETWEEN %s AND %s
            ORDER BY p.цена DESC;
            '''
            cur.execute(sql, (min_price, max_price))

        elif query_id == 7:
            # Запрос 7: Параметризованный - Товары выбранной категории
            category_id = request.args.get('category_id', 1)

            sql = '''
            SELECT 
                p.название AS "Название товара",
                p.цена AS "Цена",
                p.цвет AS "Цвет",
                p.размер AS "Размер"
            FROM product p
            WHERE p.активен = True 
                AND p.категория_id = %s
            ORDER BY p.название;
            '''
            cur.execute(sql, (category_id,))

        elif query_id == 8:
            # Запрос 8: Параметризованный - Заказы по статусу
            status = request.args.get('status', 'создан')

            sql = '''
            SELECT 
                o.номер_заказа AS "Номер заказа",
                u.имя || ' ' || u.фамилия AS "Покупатель",
                o.общая_сумма AS "Сумма",
                o.статус AS "Статус",
                o.дата_создания AS "Дата создания"
            FROM "order" o
            JOIN "user" u ON o.пользователь_id = u.id
            WHERE o.статус = %s
            ORDER BY o.дата_создания DESC;
            '''
            cur.execute(sql, (status,))

        elif query_id == 9:
            # Запрос 9: Параметризованный - Заказы конкретного пользователя
            user_id_param = request.args.get('user_id', user_id)

            sql = '''
            SELECT 
                o.номер_заказа AS "Номер заказа",
                o.общая_сумма AS "Сумма заказа",
                o.статус AS "Статус",
                o.дата_создания AS "Дата",
                COUNT(oi.product_id) AS "Количество товаров"
            FROM "order" o
            JOIN order_items oi ON o.id = oi.order_id
            WHERE o.пользователь_id = %s
            GROUP BY o.id, o.номер_заказа, o.общая_сумма, o.статус, o.дата_создания
            ORDER BY o.дата_создания DESC;
            '''
            cur.execute(sql, (user_id_param,))

        elif query_id == 10:
            # Запрос 10: Параметризованный - Отзывы с минимальным рейтингом
            min_rating = request.args.get('min_rating', 4)

            sql = '''
            SELECT 
                p.название AS "Товар",
                u.имя || ' ' || u.фамилия AS "Автор отзыва",
                r.рейтинг AS "Оценка",
                r.комментарий AS "Комментарий",
                r.дата_создания AS "Дата"
            FROM review r
            JOIN product p ON r.товар_id = p.id
            JOIN "user" u ON r.пользователь_id = u.id
            WHERE r.одобрен = True 
                AND r.рейтинг >= %s
            ORDER BY r.рейтинг DESC, r.дата_создания DESC;
            '''
            cur.execute(sql, (min_rating,))

        else:
            cur.close()
            conn.close()
            return jsonify({'error': 'Неверный ID запроса'}), 400

        # Выполняем запросы 1-5 (без параметров)
        if query_id <= 5:
            cur.execute(sql)

        # Получаем результаты
        if cur.description:
            columns = [desc[0] for desc in cur.description]
            results = cur.fetchall()

        cur.close()
        conn.close()

        # Преобразуем результаты в список словарей для удобства
        results_list = []
        for row in results:
            row_dict = {}
            for i, col in enumerate(columns):
                row_dict[col] = row[i]
            results_list.append(row_dict)

        return render_template('query_results.html',
                               query_id=query_id,
                               columns=columns,
                               results=results_list,
                               row_count=len(results_list))

    except Exception as e:
        print(f"Ошибка выполнения запроса {query_id}: {e}")
        return render_template('query_results.html',
                               query_id=query_id,
                               error=str(e))
if __name__ == '__main__':
    app.run(debug=True)