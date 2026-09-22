import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

# ---------------------------------------------------------------------------
# RFC 6238 Time-Based One-Time Password (TOTP) Native Implementation
# ---------------------------------------------------------------------------

AMBIGUOUS_CHARS = '0O1Il'
RECOVERY_CODE_ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'


def generate_secret(length: int = 20) -> str:
    """
    Generates a cryptographically secure Base32 secret string (160-bit default).
    """
    raw_bytes = secrets.token_bytes(length)
    return base64.b32encode(raw_bytes).decode('ascii').rstrip('=')


def generate_totp(secret: str, time_step: int = 30, t0: int = 0, digits: int = 6, timestamp: float = None) -> str:
    """
    Calculates a 6-digit TOTP token per RFC 6238 / RFC 4226 (HOTP).
    """
    if timestamp is None:
        timestamp = time.time()
    
    # Normalize secret with padding if needed
    secret_clean = secret.strip().replace(' ', '').upper()
    missing_padding = len(secret_clean) % 8
    if missing_padding:
        secret_clean += '=' * (8 - missing_padding)
    
    key = base64.b32decode(secret_clean, casefold=True)
    counter = int((timestamp - t0) // time_step)
    msg = struct.pack('>Q', counter)
    
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0f
    code = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff
    
    token = str(code % (10 ** digits)).zfill(digits)
    return token


def verify_totp(token: str, secret: str, window: int = 1, time_step: int = 30, timestamp: float = None) -> bool:
    """
    Verifies a TOTP token against the secret, allowing for clock drift within +/- window steps.
    """
    if not token or not secret:
        return False
    
    token_str = str(token).strip()
    if len(token_str) != 6 or not token_str.isdigit():
        return False
    
    if timestamp is None:
        timestamp = time.time()
        
    secret_clean = secret.strip().replace(' ', '').upper()
    missing_padding = len(secret_clean) % 8
    if missing_padding:
        secret_clean += '=' * (8 - missing_padding)
        
    try:
        key = base64.b32decode(secret_clean, casefold=True)
    except Exception:
        return False

    now_step = int(timestamp // time_step)
    for step in range(now_step - window, now_step + window + 1):
        msg = struct.pack('>Q', step)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0f
        code = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff
        expected = str(code % 1000000).zfill(6)
        if hmac.compare_digest(token_str, expected):
            return True
            
    return False


def generate_recovery_codes(count: int = 8) -> list[str]:
    """
    Generates single-use alphanumeric scratch recovery codes formatted as XXXX-XXXX.
    Excludes ambiguous characters (0, O, 1, I).
    """
    codes = []
    for _ in range(count):
        part1 = ''.join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(4))
        part2 = ''.join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(4))
        codes.append(f"{part1}-{part2}")
    return codes


def build_otpauth_uri(account_name: str, secret: str, issuer: str = "DOPA") -> str:
    """
    Builds the standard otpauth:// URI for authenticator applications.
    """
    label = f"{issuer}:{account_name}"
    encoded_label = urllib.parse.quote(label)
    encoded_issuer = urllib.parse.quote(issuer)
    return f"otpauth://totp/{encoded_label}?secret={secret}&issuer={encoded_issuer}&algorithm=SHA1&digits=6&period=30"


# ---------------------------------------------------------------------------
# Pure-Python SVG QR Code Generator (Zero Pip Dependencies)
# ---------------------------------------------------------------------------

EXP_TABLE = [0] * 512
LOG_TABLE = [0] * 256
val = 1
for i in range(255):
    EXP_TABLE[i] = val
    EXP_TABLE[i + 255] = val
    LOG_TABLE[val] = i
    val = (val << 1) ^ (0x11d if (val & 0x80) else 0)


def _gf_poly_mul(p1, p2):
    res = [0] * (len(p1) + len(p2) - 1)
    for i, c1 in enumerate(p1):
        if c1 == 0:
            continue
        log_c1 = LOG_TABLE[c1]
        for j, c2 in enumerate(p2):
            if c2 == 0:
                continue
            res[i + j] ^= EXP_TABLE[log_c1 + LOG_TABLE[c2]]
    return res


def _rs_generator_poly(nsym):
    g = [1]
    for i in range(nsym):
        g = _gf_poly_mul(g, [1, EXP_TABLE[i]])
    return g


def _rs_encode(data, nsym):
    gen = _rs_generator_poly(nsym)
    res = list(data) + [0] * nsym
    for i in range(len(data)):
        coef = res[i]
        if coef != 0:
            log_c = LOG_TABLE[coef]
            for j in range(len(gen)):
                res[i + j] ^= EXP_TABLE[log_c + LOG_TABLE[gen[j]]]
    return res[len(data):]


# Version parameters for ECC Level L
VERSION_L = {
    1: (21, 26, 19, 7, 1, []),
    2: (25, 44, 34, 10, 1, [6, 18]),
    3: (29, 70, 55, 15, 1, [6, 22]),
    4: (33, 100, 80, 20, 1, [6, 26]),
    5: (37, 134, 108, 26, 1, [6, 30]),
    6: (41, 172, 136, 18, 2, [6, 34]),
}


def _choose_version(data_len):
    needed = data_len + 2
    for v in range(1, 7):
        if VERSION_L[v][2] >= needed:
            return v
    return 6


def generate_qr_matrix(text: str):
    data_bytes = text.encode('utf-8')
    ver = _choose_version(len(data_bytes))
    size, total_bytes, data_capacity, ec_per_block, num_blocks, align_coords = VERSION_L[ver]

    bits = []
    def add_bits(v, count):
        for i in reversed(range(count)):
            bits.append((v >> i) & 1)

    # Byte mode (0100) + length + payload
    add_bits(4, 4)
    add_bits(len(data_bytes), 8)
    for b in data_bytes:
        add_bits(b, 8)

    # Terminator + byte align
    rem = (data_capacity * 8) - len(bits)
    term = min(4, rem)
    add_bits(0, term)
    if len(bits) % 8 != 0:
        add_bits(0, 8 - (len(bits) % 8))

    # Pad bytes
    pad = [0xEC, 0x11]
    pad_idx = 0
    while len(bits) < data_capacity * 8:
        add_bits(pad[pad_idx % 2], 8)
        pad_idx += 1

    data_stream = []
    for i in range(0, len(bits), 8):
        byte_val = 0
        for b in bits[i:i + 8]:
            byte_val = (byte_val << 1) | b
        data_stream.append(byte_val)

    blocks_data = []
    blocks_ec = []
    block_len = data_capacity // num_blocks
    for b in range(num_blocks):
        d_slice = data_stream[b * block_len:(b + 1) * block_len]
        blocks_data.append(d_slice)
        blocks_ec.append(_rs_encode(d_slice, ec_per_block))

    final_stream = []
    for col in range(block_len):
        for b in range(num_blocks):
            final_stream.append(blocks_data[b][col])
    for col in range(ec_per_block):
        for b in range(num_blocks):
            final_stream.append(blocks_ec[b][col])

    final_bits = []
    for byte in final_stream:
        for i in reversed(range(8)):
            final_bits.append((byte >> i) & 1)

    matrix = [[None] * size for _ in range(size)]
    reserved = [[False] * size for _ in range(size)]

    def draw_finder(row, col):
        for r in range(-1, 8):
            for c in range(-1, 8):
                mr, mc = row + r, col + c
                if 0 <= mr < size and 0 <= mc < size:
                    reserved[mr][mc] = True
                    if 0 <= r <= 6 and 0 <= c <= 6:
                        if r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4):
                            matrix[mr][mc] = True
                        else:
                            matrix[mr][mc] = False
                    else:
                        matrix[mr][mc] = False

    draw_finder(0, 0)
    draw_finder(0, size - 7)
    draw_finder(size - 7, 0)

    if align_coords:
        for r in align_coords:
            for c in align_coords:
                if (r < 9 and c < 9) or (r < 9 and c >= size - 9) or (r >= size - 9 and c < 9):
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        reserved[r + dr][c + dc] = True
                        if abs(dr) == 2 or abs(dc) == 2 or (dr == 0 and dc == 0):
                            matrix[r + dr][c + dc] = True
                        else:
                            matrix[r + dr][c + dc] = False

    for i in range(8, size - 8):
        matrix[6][i] = (i % 2 == 0)
        matrix[i][6] = (i % 2 == 0)
        reserved[6][i] = True
        reserved[i][6] = True

    matrix[size - 8][8] = True
    reserved[size - 8][8] = True

    for i in range(9):
        if i != 6:
            reserved[8][i] = True
            reserved[i][8] = True
    for i in range(8):
        reserved[8][size - 1 - i] = True
        reserved[size - 1 - i][8] = True

    bit_idx = 0
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        cols = [col, col - 1]
        step = -1 if ((size - 1 - col) // 2) % 2 == 0 else 1
        rows = range(size - 1, -1, -1) if step == -1 else range(size)
        for row in rows:
            for c in cols:
                if not reserved[row][c]:
                    b = final_bits[bit_idx] if bit_idx < len(final_bits) else 0
                    bit_idx += 1
                    mask = ((row + c) % 2 == 0)
                    matrix[row][c] = bool(b ^ mask)
        col -= 2

    # Level L, Mask 0 format bits (0x77c4)
    fmt = 0x77c4
    for i in range(15):
        bit = bool((fmt >> i) & 1)
        if i <= 5:
            matrix[8][i] = bit
        elif i == 6:
            matrix[8][7] = bit
        elif i == 7:
            matrix[8][8] = bit
        elif i == 8:
            matrix[7][8] = bit
        else:
            matrix[14 - i][8] = bit

        if i <= 7:
            matrix[size - 1 - i][8] = bit
        else:
            matrix[8][size - 15 + i] = bit

    return matrix


def generate_qr_svg(text: str, scale: int = 7, margin: int = 4) -> str:
    """
    Renders the QR matrix directly to an optimized standalone SVG string.
    """
    matrix = generate_qr_matrix(text)
    size = len(matrix)
    total_size = (size + margin * 2) * scale
    
    # Generate SVG path commands for compact rendering
    path_d = []
    for r in range(size):
        for c in range(size):
            if matrix[r][c]:
                x = (c + margin) * scale
                y = (r + margin) * scale
                path_d.append(f"M{x},{y}h{scale}v{scale}h-{scale}z")

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_size} {total_size}" '
        f'width="{total_size}" height="{total_size}" style="max-width: 100%; height: auto; border-radius: 8px; background: #ffffff; padding: 4px;" '
        f'role="img" aria-label="MFA Authenticator QR Code">\n'
        f'  <rect width="{total_size}" height="{total_size}" fill="#ffffff"/>\n'
        f'  <path d="{" ".join(path_d)}" fill="#0f172a"/>\n'
        f'</svg>'
    )
    return svg
