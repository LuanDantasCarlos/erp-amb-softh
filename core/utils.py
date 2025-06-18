import os
import io
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics

def fit_text_to_box(text, width_pt, height_pt, font_name, font_size):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    line_height = font_size * 1.2
    max_lines = int(height_pt // line_height)
    lines = []
    if not text:
        return lines

    paragraphs = str(text).split('\n')
    for paragraph in paragraphs:
        words = paragraph.split()
        current_line = ""
        for word in words:
            # Se palavra longa demais, força quebra
            if stringWidth(word, font_name, font_size) > width_pt:
                # Quebra a palavra em pedaços menores
                for i in range(0, len(word), 1):
                    part = word[i:i+1]
                    test_line = (current_line + part).strip()
                    if stringWidth(test_line, font_name, font_size) <= width_pt:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = part
                        if len(lines) >= max_lines:
                            break
                continue
            test_line = (current_line + " " + word).strip()
            if stringWidth(test_line, font_name, font_size) <= width_pt:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
                if len(lines) >= max_lines:
                    break
        if current_line and len(lines) < max_lines:
            lines.append(current_line)
        if len(lines) >= max_lines:
            break
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    return lines

def calcular_maxchars_textarea(width_pt, height_pt, font_name="Helvetica", font_size=12):
    texto_teste = "a" * 2000  # Texto contínuo, sem espaços
    for i in range(1, len(texto_teste)):
        test_text = texto_teste[:i]
        linhas = fit_text_to_box(test_text, width_pt, height_pt, font_name, font_size)
        total_rendered = sum(len(l) for l in linhas)
        if total_rendered < i:
            return i - 1
    return len(texto_teste)

def gerar_documento_pdf(paciente, template, campos_valores):
    try:
        if not template.arquivo_template or not os.path.exists(template.arquivo_template.path):
            print("[DEBUG] Arquivo de template não encontrado!")
            return None

        template_path = template.arquivo_template.path
        original_pdf = PdfReader(open(template_path, 'rb'))
        output = PdfWriter()

        # Agrupa posições por página, para renderizar todos os campos/posições corretamente
        campos_por_pagina = {}
        for campo in template.campos.all():
            # Suporte tanto para dict quanto para lista em campo.posicao
            posicoes = campo.posicao if isinstance(campo.posicao, list) else [campo.posicao]
            for pos in posicoes:
                pagina = pos.get('pagina', getattr(campo, 'pagina', 1) or 1)
                campos_por_pagina.setdefault(pagina, []).append({'campo': campo, 'pos': pos})

        num_paginas = len(original_pdf.pages)

        for i in range(num_paginas):
            pagina_num = i + 1
            page = original_pdf.pages[i]

            media_box = page.mediabox
            width_pdf = float(media_box.width)
            height_pdf = float(media_box.height)

            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(width_pdf, height_pdf))

            # Renderiza todos os campos/posições desta página
            for item in campos_por_pagina.get(pagina_num, []):
                campo = item['campo']
                pos = item['pos']
                valor = campos_valores.get(str(campo.id), '')
                if not valor and hasattr(campo, "atributo_paciente") and campo.atributo_paciente:
                    valor = getattr(paciente, campo.atributo_paciente, '')

                x = pos.get('x', 0)
                y = pos.get('y', 0)
                font_size = pos.get('font_size', 12)
                font_name = pos.get('font_name', 'Helvetica')
                y_rl = height_pdf - y  # Inverte Y para coordenada do PDF
                width = pos.get('width', 300)
                height = pos.get('height', 60)

                if campo.tipo_campo == 'textarea':
                    # Opcional: calcular máximo de caracteres e debugar
                    # calcular_maxchars_textarea(width, height, font_name, font_size)

                    # Opcional: desenhar retângulo da área do campo (debug)
                    # can.setStrokeColorRGB(1,0,0)
                    # can.rect(x, y_rl - height, width, height, stroke=1, fill=0)

                    linhas = fit_text_to_box(valor, width, height, font_name, font_size)
                    for idx, linha in enumerate(linhas):
                        if idx * font_size * 1.2 >= height:
                            break
                        can.setFont(font_name, font_size)
                        can.drawString(x, y_rl - idx * font_size * 1.2, linha)
                elif campo.tipo_campo == 'checkbox':
                    opcoes_marcadas = campos_valores.get(str(campo.id), [])
                    if not isinstance(opcoes_marcadas, list):
                        opcoes_marcadas = [opcoes_marcadas]
                    for opcao in campo.opcoes or []:
                        opcao_id = str(opcao.get('id', ''))
                        pos_opcao = opcao.get('posicao', {})
                        x_op = pos_opcao.get('x', x)
                        y_op = pos_opcao.get('y', y)
                        font_size_op = pos_opcao.get('font_size', font_size)
                        font_name_op = pos_opcao.get('font_name', font_name)
                        y_rl_op = height_pdf - y_op
                        if opcao_id in opcoes_marcadas:
                            can.setFont(font_name_op, font_size_op)
                            can.drawString(x_op, y_rl_op, "X")
                else:
                    can.setFont(font_name, font_size)
                    can.drawString(x, y_rl, str(valor or ''))

            can.save()
            packet.seek(0)
            overlay_pdf = PdfReader(packet)
            overlay_page = overlay_pdf.pages[0]
            page.merge_page(overlay_page)
            output.add_page(page)

        final_buffer = io.BytesIO()
        output.write(final_buffer)
        final_buffer.seek(0)
        return final_buffer

    except Exception as e:
        print(f"[ERRO] Erro ao gerar documento: {str(e)}")
        return None