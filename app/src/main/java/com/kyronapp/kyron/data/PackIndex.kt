package com.kyronapp.kyron.data

import android.content.Context
import android.util.Base64
import org.json.JSONObject
import java.security.KeyFactory
import java.security.PublicKey
import java.security.Signature
import java.security.spec.X509EncodedKeySpec

/**
 * Signed pack index (index.json + index.json.sig) published next to the
 * region packs on the `data-packs` GitHub Release. The signature is
 * ECDSA P-256 / SHA-256 (DER, base64) over the exact index.json bytes,
 * produced by tools/packs/publish_index.py with the PACK_SIGNING_KEY
 * secret, and checked here against the public key bundled in
 * assets/pack_index_pub.pem. A pack is only installed when the index
 * verifies AND lists the same sha256 as the manifest — so a compromised
 * or tampered host cannot push data into the app. Local-only: nothing is
 * sent anywhere, this only reads public files.
 */
object PackIndex {
    const val PUBLIC_KEY_ASSET = "pack_index_pub.pem"

    fun loadPublicKey(context: Context): PublicKey? = runCatching {
        val pem = context.assets.open(PUBLIC_KEY_ASSET).bufferedReader().use { it.readText() }
        parsePublicKey(pem)
    }.getOrNull()

    fun parsePublicKey(pem: String): PublicKey {
        val b64 = pem.lines().filter { it.isNotBlank() && !it.startsWith("-----") }.joinToString("")
        val der = Base64.decode(b64, Base64.DEFAULT)
        return KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(der))
    }

    fun verify(indexBytes: ByteArray, sigBase64: String, key: PublicKey): Boolean = runCatching {
        val sig = Signature.getInstance("SHA256withECDSA")
        sig.initVerify(key)
        sig.update(indexBytes)
        sig.verify(Base64.decode(sigBase64.trim(), Base64.DEFAULT))
    }.getOrDefault(false)

    /**
     * Throws unless [indexBytes] verifies under [key] and lists [regionId]
     * with exactly [sha256] (lowercase hex).
     */
    fun requireListed(indexBytes: ByteArray, sigBase64: String, key: PublicKey,
                      regionId: String, sha256: String) {
        check(verify(indexBytes, sigBase64, key)) { "Pack index signature is invalid" }
        val entry = JSONObject(String(indexBytes, Charsets.UTF_8))
            .optJSONObject("packs")?.optJSONObject(regionId)
            ?: throw IllegalStateException("Region $regionId is not in the signed pack index")
        check(entry.optString("sha256").lowercase() == sha256.lowercase()) {
            "Pack checksum does not match the signed index"
        }
    }
}
