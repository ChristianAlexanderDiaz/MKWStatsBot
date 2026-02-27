"""Score pairing for OCR - matching validated player names with their scores."""

import logging


class ScorePairer:
    """Pairs validated player names with scores using sequential flow matching with spatial disambiguation."""

    def get_bbox_center_x(self, bbox) -> float:
        """Calculate horizontal center of a bounding box."""
        if not bbox or len(bbox) < 4:
            return 0.0
        if isinstance(bbox[0], list):
            x_coords = [point[0] for point in bbox]
            return sum(x_coords) / len(x_coords)
        else:
            return (bbox[0] + bbox[2]) / 2.0

    def get_bbox_center_y(self, bbox) -> float:
        """Calculate vertical center of a bounding box."""
        if not bbox or len(bbox) < 4:
            return 0.0
        if isinstance(bbox[0], list):
            y_coords = [point[1] for point in bbox]
            return sum(y_coords) / len(y_coords)
        else:
            return (bbox[1] + bbox[3]) / 2.0

    def pair_names_with_scores(
        self,
        valid_names: list[tuple],
        score_positions: list[int],
        tokens: list[str],
        token_bboxes: dict[int, list] | None = None
    ) -> list[dict]:
        """Pair validated player names with scores using sequential flow matching with spatial disambiguation."""
        results = []
        used_scores = set()

        if token_bboxes is None:
            token_bboxes = {}

        # Sort names by position to process in reading order
        valid_names_sorted = sorted(valid_names, key=lambda x: x[0])

        for name_match in valid_names_sorted:
            # All matches are 5-element tuples: (pos, name, raw_name, embedded_score, race_count)
            name_pos, official_name, raw_name, embedded_score, race_count = name_match

            if embedded_score is not None:
                # Use the embedded score directly for multi-token corrupted sequences
                score = embedded_score
                results.append({
                    'name': official_name,
                    'raw_name': raw_name,
                    'score': score,
                    'races': race_count,
                    'raw_line': f"{raw_name} {score}",
                    'preset_used': 'database_validated',
                    'confidence': 1.0,
                    'is_roster_member': True
                })
                logging.info(f"🎯 Used embedded score: '{official_name}' (raw: '{raw_name}') with embedded score {score} ({race_count} races)")
                continue

            # Find the closest available score with priority for positional order
            best_score_pos = None
            best_after_pos = None
            best_before_pos = None
            min_after_distance = float('inf')
            min_before_distance = float('inf')

            for score_pos in score_positions:
                if score_pos not in used_scores:
                    if score_pos > name_pos:
                        distance = score_pos - name_pos
                        if distance < min_after_distance:
                            min_after_distance = distance
                            best_after_pos = score_pos
                    else:
                        distance = name_pos - score_pos
                        if distance <= 2 and distance < min_before_distance:
                            min_before_distance = distance
                            best_before_pos = score_pos

            # Prioritize based on distance and spatial position
            if min_after_distance == 1 and min_before_distance == 1:
                # Both immediately adjacent - use bbox horizontal position to disambiguate
                name_bbox = token_bboxes.get(name_pos)
                after_bbox = token_bboxes.get(best_after_pos)
                before_bbox = token_bboxes.get(best_before_pos)

                if name_bbox and after_bbox and before_bbox:
                    name_center_x = self.get_bbox_center_x(name_bbox)
                    after_center_x = self.get_bbox_center_x(after_bbox)
                    before_center_x = self.get_bbox_center_x(before_bbox)

                    if after_center_x > name_center_x and before_center_x < name_center_x:
                        best_score_pos = best_after_pos
                        logging.info(f"🎯 Bbox disambiguation: chose after score at pos {best_after_pos} (x={after_center_x:.1f} > name x={name_center_x:.1f})")
                    elif before_center_x < name_center_x and after_center_x <= name_center_x:
                        best_score_pos = best_before_pos
                        logging.info(f"🎯 Bbox disambiguation: chose before score at pos {best_before_pos} (x={before_center_x:.1f} < name x={name_center_x:.1f})")
                    else:
                        # Ambiguous horizontal position - use vertical distance as tiebreaker
                        name_center_y = self.get_bbox_center_y(name_bbox)
                        after_center_y = self.get_bbox_center_y(after_bbox)
                        before_center_y = self.get_bbox_center_y(before_bbox)

                        after_y_dist = abs(after_center_y - name_center_y)
                        before_y_dist = abs(before_center_y - name_center_y)

                        if after_y_dist < before_y_dist:
                            best_score_pos = best_after_pos
                            logging.info(f"🎯 Bbox disambiguation (y-tiebreak): chose after score at pos {best_after_pos} (y_dist={after_y_dist:.1f} < {before_y_dist:.1f})")
                        else:
                            best_score_pos = best_before_pos
                            logging.info(f"🎯 Bbox disambiguation (y-tiebreak): chose before score at pos {best_before_pos} (y_dist={before_y_dist:.1f} < {after_y_dist:.1f})")
                else:
                    best_score_pos = best_after_pos
                    logging.info("⚠️ Bbox disambiguation fallback: missing bbox data, defaulting to after score")
            elif min_after_distance == 1:
                best_score_pos = best_after_pos
            elif min_before_distance == 1:
                best_score_pos = best_before_pos
            elif best_after_pos is not None:
                best_score_pos = best_after_pos
            elif best_before_pos is not None:
                best_score_pos = best_before_pos

            if best_score_pos is not None:
                score = int(tokens[best_score_pos])
                results.append({
                    'name': official_name,
                    'raw_name': raw_name,
                    'score': score,
                    'races': race_count,
                    'raw_line': f"{raw_name} {score}",
                    'preset_used': 'database_validated',
                    'confidence': 1.0,
                    'is_roster_member': True
                })
                used_scores.add(best_score_pos)
                logging.info(f"🎯 Paired '{official_name}' (raw: '{raw_name}') at pos {name_pos} with score {score} at pos {best_score_pos} ({race_count} races)")
            else:
                logging.warning(f"⚠️ No available score found for '{official_name}'")

        return results
