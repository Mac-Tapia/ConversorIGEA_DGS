from igea_dgs.dgs import write_dgs


def _generated(model, tmp_path):
    p = tmp_path / f'{model.name}.dgs'
    write_dgs(model, p)
    return p


def test_clean_sample_passes_strict_validation(sample_model, tmp_path):
    from igea_dgs.validate import validate_dgs

    p = _generated(sample_model, tmp_path)
    report = validate_dgs(sample_model, p)
    assert report['structural_errors'] == []
    assert report['connection_errors'] == []
    assert report['schema_errors'] == []
    assert report['counts']['dgs_lines'] == len(sample_model.lines)
    assert report['counts']['dgs_loads'] == len(sample_model.loads)
    assert report['counts']['dgs_switches'] == len(sample_model.devices)
    assert report['runtime_reference_dependency'] is False


def test_duplicate_fid_is_detected(sample_model, tmp_path):
    from igea_dgs.validate import validate_dgs

    p = _generated(sample_model, tmp_path)
    lines = p.read_text(encoding='utf-8').splitlines()
    data = [i for i, line in enumerate(lines) if line.startswith('  ') and ';C;' in line]
    first = lines[data[0]].split(';')[0]
    parts = lines[data[1]].split(';')
    parts[0] = first
    lines[data[1]] = ';'.join(parts)
    p.write_text('\n'.join(lines), encoding='utf-8')
    report = validate_dgs(sample_model, p)
    assert any('duplicate FID' in e for e in report['structural_errors'])


def test_dangling_type_pointer_is_detected(sample_model, tmp_path):
    from igea_dgs.validate import validate_dgs, parse_dgs

    p = _generated(sample_model, tmp_path)
    tables = parse_dgs(p)
    target = tables['ElmLne']['rows'][0]
    old = ';'.join(target)
    typ_i = tables['ElmLne']['fields'].index('typ_id')
    target[typ_i] = '99999999'
    text = p.read_text(encoding='utf-8').replace(old, ';'.join(target), 1)
    p.write_text(text, encoding='utf-8')
    report = validate_dgs(sample_model, p)
    assert any('missing TypLne' in e for e in report['connection_errors'])


def test_missing_line_cubic_is_detected(sample_model, tmp_path):
    from igea_dgs.validate import validate_dgs, parse_dgs

    p = _generated(sample_model, tmp_path)
    tables = parse_dgs(p)
    line_fid = tables['ElmLne']['rows_dict'][0]['FID']
    cubic = next(r for r in tables['StaCubic']['rows'] if r[tables['StaCubic']['fields'].index('obj_id')] == line_fid)
    text = p.read_text(encoding='utf-8').replace('  ' + ';'.join(cubic) + '\n', '', 1)
    p.write_text(text, encoding='utf-8')
    report = validate_dgs(sample_model, p)
    assert any('cubicles' in e for e in report['connection_errors'])


def test_switch_parent_must_be_a_cubic(sample_model, tmp_path):
    from igea_dgs.validate import validate_dgs, parse_dgs

    if not sample_model.devices:
        return
    p = _generated(sample_model, tmp_path)
    tables = parse_dgs(p)
    row = tables['StaSwitch']['rows'][0]
    old = ';'.join(row)
    fold_i = tables['StaSwitch']['fields'].index('fold_id')
    row[fold_i] = tables['ElmTerm']['rows_dict'][0]['FID']
    p.write_text(p.read_text(encoding='utf-8').replace(old, ';'.join(row), 1), encoding='utf-8')
    report = validate_dgs(sample_model, p)
    assert any('StaSwitch' in e and 'StaCubic' in e for e in report['connection_errors'])


def test_line_length_mismatch_is_detected(sample_model, tmp_path):
    from igea_dgs.validate import validate_dgs, parse_dgs

    p = _generated(sample_model, tmp_path)
    tables = parse_dgs(p)
    row = tables['ElmLne']['rows'][0]
    old = ';'.join(row)
    dline_i = tables['ElmLne']['fields'].index('dline')
    row[dline_i] = str(float(row[dline_i]) + 1.0)
    p.write_text(p.read_text(encoding='utf-8').replace(old, ';'.join(row), 1), encoding='utf-8')
    report = validate_dgs(sample_model, p)
    assert any('length' in e.lower() for e in report['structural_errors'])
