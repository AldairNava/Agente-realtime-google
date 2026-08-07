import sys

try:
    with open('src/agent_core.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    start_idx = -1
    for i, line in enumerate(lines):
        if 'if self.campania_name == \'plata\':' in line and 'OMITIDO TEMPORALMENTE' in lines[i+1]:
            start_idx = i
            break
            
    if start_idx == -1:
        print('Could not find bypass block')
        sys.exit(1)

    else_idx = -1
    for i in range(start_idx, len(lines)):
        if 'else:' in lines[i] and 'new_client_found = False' in lines[i+1]:
            else_idx = i
            break

    end_idx = -1
    for i in range(else_idx, len(lines)):
        if 'await asyncio.to_thread(self.phantom.go_to_main_tab)' in lines[i]:
            end_idx = i
            break

    new_lines = []
    new_lines.extend(lines[:start_idx])
    
    # We unindent the lines from else_idx+1 to end_idx by 4 spaces
    for i in range(else_idx+1, end_idx):
        if lines[i].startswith('    '):
            new_lines.append(lines[i][4:])
        else:
            new_lines.append(lines[i])

    # Now add the override for plata
    new_lines.append('                                                    if self.campania_name == \'plata\':\n')
    new_lines.append('                                                        if not first_name or first_name.upper() in ("TITULAR", "PROSPECTO", "CLIENTE", "DESCONOCIDO", "UNKNOWN", "TEST", ""):\n')
    new_lines.append('                                                            first_name = "Diego"\n')
    new_lines.append('                                                            last_name = "Garcia"\n')
    
    new_lines.append(lines[end_idx]) # await asyncio.to_thread(self.phantom.go_to_main_tab)
    
    # Keep the rest of the lines
    new_lines.extend(lines[end_idx+1:])
    
    # Let's also fix the greeting phrase
    for i in range(len(new_lines)):
        if 'greeting_phrase = "Hola, buenas tardes, me presento mi nombre es Liliana Hernández, ¿tengo el gusto con Alfredo?"' in new_lines[i]:
            new_lines[i] = new_lines[i].replace('greeting_phrase = "Hola, buenas tardes, me presento mi nombre es Liliana Hernández, ¿tengo el gusto con Alfredo?"', 'greeting_phrase = f"Hola, buenas tardes, me presento mi nombre es Liliana Hernández, ¿tengo el gusto con {first_name} {last_name}?"')

    with open('src/agent_core.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print('Reverted bypass successfully.')

except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
