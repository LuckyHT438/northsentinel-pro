# ============================================================
# MAIN — BOUCLE CONTINUE AVEC SCANS ESPACÉS DE 60 MIN
# ============================================================

def main():
    now = datetime.now(MONTREAL_TZ)
    heure = now.hour
    minute = now.minute

    if is_ca_market_closed(now):
        print("🏖️ Marché CA fermé – Arrêt.", flush=True)
        if IS_MANUAL_RUN:
            msg = (
                "🤖 <b>NorthSentinel CA Only</b>™\n"
                "<i>Canadian intraday trading signals. Long & Short. Manual execution.</i>\n"
                f"<i>📅 {now.strftime('%Y-%m-%d %H:%M')} (Montreal) | 💰 Capital: ${CAPITAL:,.0f}</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "⏰ Manual run triggered on a closed market day.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Informational automated signal. Not financial or trading advice.</i>"
            )
            send_telegram(msg)
        return

    early_close = is_early_close(now)
    early_hour = get_early_close_hour(now) if early_close else None
    if early_close:
        print(f"⚠️ Fermeture anticipée – Marché ferme à {early_hour}:00 ET.", flush=True)

    # =========================================================
    # HORAIRES
    # AM : 09:25 → 11:30 (3 scans : 09:30, 10:30, 11:30)
    # PM : 14:00 → 15:00 (2 scans : 14:00, 15:00)
    # =========================================================
    if 9 <= heure <= 11 and (heure < 11 or minute <= 35):
        session = "morning"
        start_hour, start_min = 9, 25
        end_hour, end_min = 11, 30
        scan_hours = [9, 10, 11]
        scan_minutes = [30, 30, 30]
        print("☀️ Session MATIN détectée – Scans à 09:30, 10:30, 11:30.", flush=True)
    elif 14 <= heure <= 15 and (heure < 15 or minute <= 5):
        session = "afternoon"
        start_hour, start_min = 14, 0
        end_hour, end_min = 15, 0
        if early_close and early_hour is not None and early_hour <= 14:
            print(f"🌙 Session PM annulée – early close à {early_hour}:00 ET.", flush=True)
            return
        scan_hours = [14, 15]
        scan_minutes = [0, 0]
        print("🌙 Session APRÈS-MIDI détectée – Scans à 14:00, 15:00.", flush=True)
    else:
        print(f"⏰ Hors plage horaire ({now.strftime('%H:%M')}) – Arrêt.", flush=True)
        if IS_MANUAL_RUN:
            msg = (
                "🤖 <b>NorthSentinel CA Only</b>™\n"
                "<i>Canadian intraday trading signals. Long & Short. Manual execution.</i>\n"
                f"<i>📅 {now.strftime('%Y-%m-%d %H:%M')} (Montreal)</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "⏰ Manual run triggered outside trading hours.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Informational automated signal. Not financial or trading advice.</i>"
            )
            send_telegram(msg)
        return

    # =========================================================
    # ATTENTE DU DÉBUT DE SESSION SI LANCÉ TROP TÔT
    # =========================================================
    now = datetime.now(MONTREAL_TZ)
    if now.hour < start_hour or (now.hour == start_hour and now.minute < start_min):
        wait_until_target(start_hour, start_min)

    # =========================================================
    # BOUCLE PRINCIPALE
    # =========================================================
    while True:
        now = datetime.now(MONTREAL_TZ)

        # Fin de session
        if now.hour > end_hour or (now.hour == end_hour and now.minute > end_min):
            print(f"⏹️ Fin de session ({end_hour:02d}:{end_min:02d}) – Arrêt.", flush=True)
            send_session_end_message(now, session)
            break

        current_hour, current_min = now.hour, now.minute

        # Vérifier si on est dans un créneau de scan (tolérance 5 min)
        is_scan_time = False
        current_total = current_hour * 60 + current_min
        for h, m in zip(scan_hours, scan_minutes):
            slot_total = h * 60 + m
            if 0 <= current_total - slot_total <= 5:
                is_scan_time = True
                break

        if is_scan_time:
            print(f"\n📊 Scan à {now.strftime('%H:%M')} (session {session})", flush=True)

            # ---- STOCKS ----
            stocks_results = []
            for ticker in STOCK_TICKERS:
                print(f"  - {ticker}:", flush=True)
                data = analyze_stock(ticker, verbose=True)
                if data:
                    stocks_results.append(data)
                    print(f"    ✅ Score {data['score']}/7 | {data['direction']} | TP: {data['tp_pct']}% | SL: {data['sl_pct']}%", flush=True)
                else:
                    print("    ❌", flush=True)

            # ---- ETFs ----
            etfs_results = []
            for ticker in ETF_TICKERS:
                print(f"  - {ticker}...", end=" ", flush=True)
                data = analyze_etf(ticker)
                if data:
                    etfs_results.append(data)
                    print(f"✅ Score {data['score']}/5 | {data['direction']} | TP: {data['tp_pct']}% | SL: {data['sl_pct']}%", flush=True)
                else:
                    print("❌", flush=True)

            # ---- SYNTHETIC L2 ----
            print("\n🧠 ================================", flush=True)
            print("🧠 SYNTHETIC L2 — STOCKS", flush=True)
            print("🧠 ================================", flush=True)
            stocks_results = enrich_with_synthetic_l2(stocks_results, is_etf=False)
            print("\n🧠 ================================", flush=True)
            print("🧠 SYNTHETIC L2 — ETFs", flush=True)
            print("🧠 ================================", flush=True)
            etfs_results = enrich_with_synthetic_l2(etfs_results, is_etf=True)

            # ---- SÉLECTION ----
            stock_long = [s for s in stocks_results if s["direction"] == "LONG"]
            stock_short = [s for s in stocks_results if s["direction"] == "SHORT"]
            etf_long = [e for e in etfs_results if e["direction"] == "LONG"]
            etf_short = [e for e in etfs_results if e["direction"] == "SHORT"]

            def get_best(candidates, is_etf):
                if not candidates:
                    return None
                scored = []
                for cand in candidates:
                    ps = calculate_priority_score(cand, "⚪ Neutral", is_etf)
                    scored.append((ps, cand))
                scored.sort(key=lambda x: x[0], reverse=True)
                return scored[0][1]

            best_stock_long = get_best(stock_long, False)
            best_stock_short = get_best(stock_short, False)
            best_etf_long = get_best(etf_long, True)
            best_etf_short = get_best(etf_short, True)

            possible_pairs = []
            threshold = SYNTHETIC_L2_CONFIG["priority_threshold_for_pair"]

            if best_stock_long and best_etf_short:
                score_stock = calculate_priority_score(best_stock_long, "⚪ Neutral", False)
                score_etf = calculate_priority_score(best_etf_short, "⚪ Neutral", True)
                if score_stock >= threshold and score_etf >= threshold:
                    possible_pairs.append((best_stock_long, best_etf_short, score_stock + score_etf))

            if best_stock_short and best_etf_long:
                score_stock = calculate_priority_score(best_stock_short, "⚪ Neutral", False)
                score_etf = calculate_priority_score(best_etf_long, "⚪ Neutral", True)
                if score_stock >= threshold and score_etf >= threshold:
                    possible_pairs.append((best_stock_short, best_etf_long, score_stock + score_etf))

            selected_stock = None
            selected_etf = None

            if possible_pairs:
                best_pair = max(possible_pairs, key=lambda x: x[2])
                selected_stock, selected_etf = best_pair[0], best_pair[1]
            else:
                all_stocks = [s for s in stocks_results]
                all_etfs = [e for e in etfs_results]
                selected_stock = get_best(all_stocks, False)
                selected_etf = get_best(all_etfs, True)

            # ---- MESSAGE TELEGRAM ----
            msg = "🤖 <b>NorthSentinel CA Only</b>™\n"
            msg += "<i>Canadian intraday trading signals. Long & Short. Manual execution.</i>\n"
            msg += f"📅 {now.strftime('%Y-%m-%d %H:%M')} (Montreal) | Scanned: {len(STOCK_TICKERS)} Stocks, {len(ETF_TICKERS)} ETFs\n"
            msg += f"Capital: ${CAPITAL:,.0f} (Paper Trading Account)\n"
            msg += "═══════════════════════════════════\n"

            msg += "\n🚀 <b>BEST STOCK SETUP</b>\n"
            if selected_stock:
                rank = "1/2" if selected_etf else "1/1"
                msg += build_setup_message(selected_stock, is_etf=False, bias="⚪ Neutral", rank=rank)
            else:
                msg += "   <i>Aucun setup STOCK valide trouvé.</i>\n"

            msg += "\n🚀 <b>BEST ETF SETUP</b>\n"
            if selected_etf:
                rank = "2/2" if selected_stock else "1/1"
                msg += build_setup_message(selected_etf, is_etf=True, bias="⚪ Neutral", rank=rank)
            else:
                msg += "   <i>Aucun setup ETF valide trouvé.</i>\n"

            msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            msg += "<i>Informational automated signal. Not financial or trading advice.</i>"
            send_telegram(msg)

        # ---- PROCHAINE CIBLE ----
        next_scan_time = None
        for h, m in zip(scan_hours, scan_minutes):
            if h > current_hour or (h == current_hour and m > current_min):
                next_scan_time = (h, m)
                break

        if next_scan_time is None:
            # Plus de scan programmé → attendre la fin de session
            # On va s'endormir jusqu'à end_hour:end_min, puis la boucle s'arrêtera
            print("⏳ Plus aucun scan programmé – Attente de la fin de session.", flush=True)
            time.sleep(60)
            continue

        target_hour, target_min = next_scan_time

        # Si le prochain scan est après la fin, on s'arrête
        if target_hour > end_hour or (target_hour == end_hour and target_min > end_min):
            print("⏹️ Prochaine cible après la fin de session – Arrêt.", flush=True)
            send_session_end_message(now, session)
            break

        wait_until_target(target_hour, target_min)
