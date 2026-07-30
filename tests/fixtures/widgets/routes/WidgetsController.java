// CI e2e 픽스처: LLM 서브에이전트가 만들 컨트롤러를 대신하는 손으로 쓴 최소 구현.
// scaffold+verify_backend.py 파이프라인 자체를 회귀 검증하기 위한 것 - 실제 도메인
// 생성 품질과는 무관하다.
package com.example.todo.widgets;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;
import java.util.Map;

@RestController
public class WidgetsController {
    private final JdbcTemplate jdbcTemplate;

    public WidgetsController(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    record WidgetIn(@NotNull String name, @NotNull Integer quantity) {}
    record QuantityIn(@NotNull Integer quantity) {}
    record Widget(long id, String name, int quantity) {}

    @PostMapping("/widgets")
    public ResponseEntity<Widget> create(@Valid @RequestBody WidgetIn body) {
        if (body.name().isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "name은 필수입니다");
        }
        if (body.quantity() < 0) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "quantity는 0 이상이어야 합니다");
        }
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(con -> {
            PreparedStatement ps = con.prepareStatement(
                "INSERT INTO widget (name, quantity) VALUES (?, ?)", new String[]{"id"});
            ps.setString(1, body.name());
            ps.setInt(2, body.quantity());
            return ps;
        }, keyHolder);
        long id = keyHolder.getKey().longValue();
        return ResponseEntity.status(201).body(new Widget(id, body.name(), body.quantity()));
    }

    @GetMapping("/widgets")
    public Map<String, List<Widget>> list() {
        List<Widget> widgets = jdbcTemplate.query(
            "SELECT id, name, quantity FROM widget",
            (rs, rowNum) -> new Widget(rs.getLong("id"), rs.getString("name"), rs.getInt("quantity")));
        return Map.of("widgets", widgets);
    }

    @PutMapping("/widgets/{id}")
    public Widget update(@PathVariable long id, @Valid @RequestBody QuantityIn body) {
        int updated = jdbcTemplate.update("UPDATE widget SET quantity = ? WHERE id = ?", body.quantity(), id);
        if (updated == 0) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "위젯을 찾을 수 없습니다");
        }
        try {
            return jdbcTemplate.queryForObject(
                "SELECT id, name, quantity FROM widget WHERE id = ?",
                (rs, rowNum) -> new Widget(rs.getLong("id"), rs.getString("name"), rs.getInt("quantity")),
                id);
        } catch (EmptyResultDataAccessException e) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "위젯을 찾을 수 없습니다");
        }
    }
}
