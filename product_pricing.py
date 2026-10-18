GAJO_OPTION = 'Cambiar a papas gajo (+$7)'


def unit_price(product, notes=''):
    selected = GAJO_OPTION in notes.split(', ')
    if selected and product['category'] != 'Hamburguesas con papas':
        raise ValueError('El cambio a papas gajo solo aplica a hamburguesas con papas.')
    return product['price'] + (700 if selected else 0)
