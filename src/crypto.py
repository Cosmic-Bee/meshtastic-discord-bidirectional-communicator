import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from meshtastic.protobuf import mesh_pb2

def decrypt_packet(mesh_packet, key_b64):
    if not mesh_packet.HasField("encrypted"):
        return mesh_packet.decoded if mesh_packet.HasField("decoded") else None

    try:
        key_bytes = base64.b64decode(key_b64.encode('ascii'))
        packet_id = getattr(mesh_packet, "id").to_bytes(8, "little")
        sender_id = getattr(mesh_packet, "from").to_bytes(8, "little")
        nonce = packet_id + sender_id
        
        cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(nonce), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_bytes = decryptor.update(mesh_packet.encrypted) + decryptor.finalize()
        
        decoded_data = mesh_pb2.Data()
        decoded_data.ParseFromString(decrypted_bytes)
        return decoded_data
    except Exception as e:
        print(f"⚠️ Native decryption failed: {e}")
        return None